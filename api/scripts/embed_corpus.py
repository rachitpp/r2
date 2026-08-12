"""Load `corpus/` into the two Phase 3 tables. No model calls, no key, no quota.

Two things land here, and they come from different files on purpose:

  supplier_term_clauses  <- corpus/extracted/*.json, the clause-level provenance
                            Phase 2 proved was needed. What each document SAYS.
  doc_chunks             <- corpus/parsed/*.md, chunked and embedded locally
                            with bge-small-en-v1.5 (CPU, 384d).

**Embeddings are local, so this is free and repeatable** (CLAUDE.md rule 2). The
first run downloads the model from HuggingFace; that is a model download, not a
model call, and nothing here needs a credential.

**Idempotent by content hash.** A chunk whose text has not changed keeps its
existing vector, so a re-run after a parse change re-embeds only what moved and
"the parse drifted underneath the embeddings" is visible rather than silent.

Rule 7 is enforced at load time rather than trusted: every chunk gets the
document's `effective_from` / `effective_to` from `MANIFEST.csv`, and a document
with no effective_from is refused rather than defaulted — a chunk with an
invented validity period is worse than a missing one, because demo beat 2 rests
on "no document in force" being distinguishable from "not found".
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "api" / "src"))

from pos_copilot.embed import (  # noqa: E402
    chunk_markdown,
    content_hash,
    default_embedder,
)

CORPUS = REPO_ROOT / "corpus"

# doc_id carries the supplier: `contract-sup-01-20241130` -> SUP-01. Policies
# carry none, and that NULL is meaningful — a policy applies chain-wide, so a
# supplier-scoped query must match NULL as well or it silently drops every one.
SUPPLIER_IN_DOC_ID = re.compile(r"-sup-(\d+)-")


def supplier_code_for(doc_id: str) -> str | None:
    found = SUPPLIER_IN_DOC_ID.search(doc_id)
    return f"SUP-{found.group(1)}" if found else None


def load_manifest(corpus: Path) -> list[dict]:
    with (corpus / "MANIFEST.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_clauses(conn, corpus: Path, supplier_ids: dict[str, int]) -> tuple[int, int]:
    """Populate supplier_term_clauses from the committed extractions."""
    extracted = corpus / "extracted"
    written = skipped = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM supplier_term_clauses")
        for path in sorted(extracted.glob("contract-*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            doc_id = path.stem
            code = data.get("supplier_code") or supplier_code_for(doc_id)
            supplier_id = supplier_ids.get(code or "")
            if supplier_id is None:
                # contract-sup-01-20241130 extracts supplier_code: null because
                # OCR lost the letterhead (corpus/corrections/). The doc_id
                # still names the supplier, so the fallback above resolves it —
                # if BOTH are missing the row is skipped rather than guessed.
                skipped += 1
                continue
            if not data.get("effective_from"):
                skipped += 1
                continue
            for clause in data.get("clauses") or []:
                if not isinstance(clause, dict) or not clause.get("clause"):
                    continue
                value = clause.get("value")
                numeric = value if isinstance(value, (int, float)) else None
                text = None if numeric is not None else (value and str(value))
                if numeric is None and text is None:
                    continue
                cur.execute(
                    """insert into supplier_term_clauses
                       (supplier_id, doc_id, clause, clause_number, value_numeric,
                        value_text, verbatim, effective_from, effective_to)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        supplier_id,
                        doc_id,
                        clause["clause"],
                        clause.get("clause_number"),
                        numeric,
                        text,
                        clause.get("verbatim") or "",
                        data["effective_from"],
                        data.get("effective_to"),
                    ),
                )
                written += 1
    return written, skipped


def store_ids_for_invoices(conn, manifest: list[dict]) -> dict[str, int]:
    """Which store each invoice was delivered to.

    **Invoices are the only store-specific documents in this corpus**, and until
    2026-08-13 nothing populated `doc_chunks.store_id` at all — every row was
    NULL. That is worse than it sounds: the scope predicate is
    `(store_id = %s OR store_id IS NULL)`, so with every row NULL a store-scoped
    query matches EVERYTHING and the restriction reads as working. A test
    written against that data would have passed for the wrong reason, which is
    the defect this project keeps finding, in a filter written the day before.

    Contracts, catalogs and policies stay NULL because they genuinely are
    chain-wide — a supply agreement is not "the Kothrud agreement". NULL means
    "applies everywhere" and the predicate must keep matching it, or a clerk
    loses every policy document.
    """
    po_ids = {
        row["doc_id"]: int(row["source_key"])
        for row in manifest
        if row["doc_type"] == "invoice" and row["source_key"]
    }
    if not po_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "select po_id, store_id from purchase_orders where po_id = ANY(%s)",
            (list(po_ids.values()),),
        )
        by_po = dict(cur.fetchall())
    return {
        doc_id: by_po[po_id] for doc_id, po_id in po_ids.items() if po_id in by_po
    }


def load_chunks(
    conn, corpus: Path, supplier_ids: dict[str, int], *, reembed: bool
) -> tuple[int, int, int]:
    """Chunk corpus/parsed/, embed what changed, upsert."""
    embedder = default_embedder()
    manifest_rows = load_manifest(corpus)
    manifest = {row["doc_id"]: row for row in manifest_rows}
    invoice_stores = store_ids_for_invoices(conn, manifest_rows)

    with conn.cursor() as cur:
        cur.execute("select doc_id, chunk_index, content_sha256 from doc_chunks")
        existing = {(r[0], r[1]): r[2] for r in cur.fetchall()}

    inserted = reused = refused = 0
    pending: list[tuple] = []

    for path in sorted((corpus / "parsed").glob("*.md")):
        doc_id = path.stem
        meta = manifest.get(doc_id)
        if not meta or not meta.get("effective_from"):
            # Refused, not defaulted. A chunk with an invented validity period
            # would answer a temporal question confidently and wrongly.
            print(f"  REFUSED {doc_id} — no effective_from in MANIFEST.csv")
            refused += 1
            continue

        effective_from = meta["effective_from"]
        effective_to = meta.get("effective_to") or None

        if effective_to == effective_from:
            # ALL TEN INVOICES ARRIVE THIS WAY, and it is not a typo in the
            # manifest — an invoice is a point-in-time document, so "dated
            # 2026-06-30" is written from=to=2026-06-30. Under the half-open
            # [from, to) semantics this schema uses everywhere, that is the
            # EMPTY range, and `valid_period @> DATE '2026-06-30'` would have
            # matched nothing. Every invoice would have been silently
            # unretrievable by date while looking perfectly well-formed.
            #
            # The CHECK constraint caught it at load time rather than letting
            # retrieval quietly return fewer documents than it should. A
            # point-in-time document covers its own day, so the day is the
            # period.
            effective_to = str(date.fromisoformat(effective_from) + timedelta(days=1))

        code = supplier_code_for(doc_id)
        chunks = chunk_markdown(path.read_text(encoding="utf-8"))
        for index, content in enumerate(chunks):
            digest = content_hash(content)
            if not reembed and existing.get((doc_id, index)) == digest:
                reused += 1
                continue
            pending.append(
                (
                    doc_id,
                    meta["doc_type"],
                    index,
                    content,
                    supplier_ids.get(code or ""),
                    invoice_stores.get(doc_id),
                    effective_from,
                    effective_to,
                    digest,
                )
            )

    if pending:
        vectors = embedder.encode([row[3] for row in pending])
        with conn.cursor() as cur:
            for row, vector in zip(pending, vectors, strict=True):
                cur.execute(
                    """insert into doc_chunks
                       (doc_id, doc_type, chunk_index, content, supplier_id,
                        store_id, effective_from, effective_to, content_sha256,
                        embedding)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict (doc_id, chunk_index) do update set
                         content = excluded.content,
                         doc_type = excluded.doc_type,
                         supplier_id = excluded.supplier_id,
                         store_id = excluded.store_id,
                         effective_from = excluded.effective_from,
                         effective_to = excluded.effective_to,
                         content_sha256 = excluded.content_sha256,
                         embedding = excluded.embedding""",
                    (*row, str(vector)),
                )
                inserted += 1
    return inserted, reused, refused


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="re-embed every chunk even if its content hash is unchanged",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("DATABASE_URL is not set.")
        return 1
    corpus = Path(args.corpus)
    if not (corpus / "extracted").is_dir():
        print("corpus/extracted/ does not exist — run `make extract` first.")
        return 1

    import psycopg

    with psycopg.connect(args.database_url, connect_timeout=30) as conn:
        with conn.cursor() as cur:
            cur.execute("select code, supplier_id from suppliers")
            supplier_ids = {r[0]: r[1] for r in cur.fetchall()}

        clauses, clause_skips = load_clauses(conn, corpus, supplier_ids)
        print(f"clauses    {clauses} rows ({clause_skips} documents skipped)")

        inserted, reused, refused = load_chunks(
            conn, corpus, supplier_ids, reembed=args.reembed
        )
        print(f"chunks     {inserted} embedded, {reused} unchanged, {refused} refused")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("select count(*), count(embedding) from doc_chunks")
            total, embedded = cur.fetchone()
            print(f"doc_chunks {total} rows, {embedded} with an embedding")
            cur.execute("select count(*) from supplier_term_clauses")
            print(f"supplier_term_clauses {cur.fetchone()[0]} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
