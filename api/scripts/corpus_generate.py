#!/usr/bin/env python3
"""Generate the synthetic corpus from the seeded database.

**These are not real documents and nothing here should imply they are.** The
corpus was originally specified as real records published with permission; that
was changed on 2026-08-09 and every claim in the repo was corrected to match.
What this script produces is a measurement substrate, and its limits are stated
in `corpus/README.md` rather than left for a reader to infer.

**Generated FROM the database, not alongside it.** Every contract corresponds to
a `supplier_terms` period, every invoice to a `purchase_orders` row and its
lines, every catalog to `supplier_prices` on a date. A document and the row it
describes therefore cannot disagree — which is the whole basis of demo beat 2
("what were the terms before the renegotiation?"), and it makes `TIMELINE.md`
verifiable by query instead of by hand. Inventing documents beside the data
would have produced a corpus that reads fine and contradicts every answer.

**Determinism follows `seed.py`.** Same `MASTER_SEED`, same sha256-derived
substreams, no `hash()`. PDFs are the awkward part: reportlab stamps a creation
timestamp by default, which alone would break byte-identity, so output metadata
is pinned and dates are fixed. Run twice, get the same bytes.

**The difficulty in here was chosen, which is a weaker thing than difficulty that
occurred.** Scans, skew, a table across a page break, totals above line items, a
bilingual document: each is listed in the manifest as an injected property, so a
reader can see exactly which hard cases the pipeline was and was not tested on.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from random import Random

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "corpus"
SOURCES = CORPUS / "sources"

MASTER_SEED = 42

#: Pinned so a regenerated corpus is byte-identical. Not "now" — never "now".
DOC_DATE = "D:20260809000000+00'00'"


def substream(*parts: object) -> Random:
    """An independent RNG derived from MASTER_SEED and a stream name.

    Copied from `seed.py` deliberately rather than imported: that module builds
    a whole dataset at import time. The rule it encodes matters here too —
    `hash()` is salted per process, sha256 is not.
    """
    key = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return Random(int.from_bytes(digest[:8], "big") ^ MASTER_SEED)


# ── What the generator is allowed to make hard ───────────────────────────────
#
# Every value here is an INJECTED property recorded in MANIFEST.csv. The list is
# the honest limit of the extraction measurement: the pipeline is tested against
# these and against nothing else.

SCANNED = "scanned-200dpi-skewed"
PAGE_BREAK_TABLE = "table-spans-page-break"
TOTALS_ABOVE = "totals-above-line-items"
BILINGUAL = "bilingual-mr-en"
SIGNATURE = "signature-block"
AMENDMENT = "clause-level-amendment"


#: Directory per type. Spelled out rather than pluralised by appending "s",
#: which produced `policys/` on the first run.
SUBDIR = {
    "contract": "contracts",
    "invoice": "invoices",
    "catalog": "catalogs",
    "policy": "policies",
}


@dataclass
class Doc:
    """One generated document, and the row it was generated from."""

    doc_id: str
    doc_type: str
    title: str
    #: What this document is evidence about, so TIMELINE.md can be checked.
    subject: str
    effective_from: date | None
    effective_to: date | None
    #: The database row this was generated from — the audit trail back to truth.
    source_table: str
    source_key: str
    difficulty: list[str] = field(default_factory=list)
    blocks: list = field(default_factory=list)
    pages: int = 0
    sha256: str = ""

    @property
    def filename(self) -> str:
        return f"{self.doc_id}.pdf"


def fetch(conn, sql: str, params: tuple = ()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def money(value: Decimal | float) -> str:
    return f"{Decimal(value):,.2f}"


# ── Content, derived from rows ───────────────────────────────────────────────


def build_contracts(conn) -> list[Doc]:
    """One contract per `supplier_terms` period, plus two clause-level amendments.

    Both shapes on purpose. `PLAN.md` wanted to know whether real suppliers amend
    or reissue, because it decides between a wide `supplier_terms` table and a
    narrow `supplier_term_clauses` one. A generated corpus cannot discover that,
    so it carries both and the pipeline gets exercised against the harder case.
    """
    rows = fetch(
        conn,
        """
        SELECT t.supplier_terms_id, t.supplier_id, s.name AS supplier, s.code,
               s.contact_email, t.payment_terms_days, t.lead_time_days,
               t.min_order_value, t.volume_discount_pct, t.returns_window_days,
               t.effective_from, t.effective_to
        FROM supplier_terms t
        JOIN suppliers s USING (supplier_id)
        ORDER BY t.supplier_id, t.effective_from
        """,
    )
    # The two suppliers whose second period arrives as an amendment rather than
    # a reissue. Fixed, not sampled: the manifest has to name them.
    amending = {4, 9}

    docs: list[Doc] = []
    for row in rows:
        superseded = row["effective_to"] is not None
        is_amendment = row["supplier_id"] in amending and not superseded
        kind = "AMENDMENT" if is_amendment else "SUPPLY AGREEMENT"
        doc_id = f"contract-{row['code'].lower()}-{row['effective_from']:%Y%m%d}"

        doc = Doc(
            doc_id=doc_id,
            doc_type="contract",
            title=f"{kind} — {row['supplier']}",
            subject=f"supplier {row['supplier_id']} terms",
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
            source_table="supplier_terms",
            source_key=str(row["supplier_terms_id"]),
        )
        if is_amendment:
            doc.difficulty.append(AMENDMENT)
        doc.blocks = contract_blocks(row, kind, is_amendment)
        docs.append(doc)

    # Injected difficulty, on specific documents so the manifest can name them.
    by_id = {d.doc_id: d for d in docs}
    for doc_id, marks in (
        (docs[0].doc_id, [SCANNED, SIGNATURE]),
        (docs[3].doc_id, [SCANNED]),
    ):
        by_id[doc_id].difficulty.extend(marks)
    return docs


# BILINGUAL is defined, rendered and verified, and is deliberately assigned to
# nothing. The build environment has no Devanagari font — only DejaVu, which
# does not cover the script — so the text came out blank and `verify_difficulty`
# refused the run. Transliterating Marathi into Latin script would have produced
# a document that carries the label and not the difficulty, which is worse than
# not having it. **The pipeline is therefore not tested on non-Latin scripts**,
# and `corpus/README.md` says so. Install a Devanagari font, add it to the
# renderer, and put the mark back on a contract to close the gap.


def contract_blocks(row: dict, kind: str, is_amendment: bool) -> list:
    """The clause list. Amendments carry only the clauses they change."""
    period = (
        f"{row['effective_from']:%d %B %Y} until further notice"
        if row["effective_to"] is None
        else f"{row['effective_from']:%d %B %Y} to {row['effective_to']:%d %B %Y}"
    )
    clauses = [
        (
            "1. Parties",
            f"Kirana Retail Chain (Maharashtra) and {row['supplier']} "
            f"({row['code']}), contact {row['contact_email']}.",
        ),
        ("2. Term", f"This agreement is in force from {period}."),
        (
            "3. Payment terms",
            f"Net {row['payment_terms_days']} days from invoice date.",
        ),
        (
            "4. Lead time",
            f"{row['lead_time_days']} days from purchase order to delivery.",
        ),
        (
            "5. Minimum order",
            f"INR {money(row['min_order_value'])} per purchase order.",
        ),
        (
            "6. Volume discount",
            f"{row['volume_discount_pct']}% on orders above the minimum.",
        ),
        ("7. Returns window", f"{row['returns_window_days']} days from receipt."),
    ]
    if is_amendment:
        # An amendment states what it replaces and nothing else. This is the
        # shape that a wide supplier_terms table cannot represent on its own.
        clauses = [
            (
                "Amendment",
                f"This amendment varies the supply agreement between the "
                f"parties with effect from {row['effective_from']:%d %B %Y}. "
                f"All clauses not varied below remain in force.",
            ),
            (
                "Clause 3 (Payment terms), as varied",
                f"Net {row['payment_terms_days']} days from invoice date.",
            ),
            (
                "Clause 4 (Lead time), as varied",
                f"{row['lead_time_days']} days from purchase order to delivery.",
            ),
            (
                "Clause 7 (Returns window), as varied",
                f"{row['returns_window_days']} days from receipt.",
            ),
        ]
    return [("heading", kind), ("meta", period), ("clauses", clauses)]


def build_invoices(conn) -> list[Doc]:
    """Ten invoices, sampled across suppliers and dates from received POs.

    Totals reconcile against `purchase_order_lines.line_total`, so an extraction
    error in a line item is detectable rather than merely plausible.
    """
    rows = fetch(
        conn,
        """
        SELECT po.po_id, po.supplier_id, s.name AS supplier, s.code,
               po.ordered_on, po.received_on, po.subtotal, po.store_id,
               st.name AS store, st.city
        FROM purchase_orders po
        JOIN suppliers s USING (supplier_id)
        JOIN stores st USING (store_id)
        WHERE po.status = 'received'
        ORDER BY po.po_id
        """,
    )
    picker = substream("invoice-pick")
    by_id = {r["po_id"]: r for r in rows}
    # The largest order in the data, included on purpose. The page-break case
    # needs a table with enough rows to actually cross a boundary, and a random
    # sample of ten gave nothing near it — the first run advertised the
    # difficulty on a single-page invoice.
    with conn.cursor() as cur:
        cur.execute(
            """SELECT po_id FROM purchase_order_lines
               WHERE po_id = ANY(%s) GROUP BY po_id
               ORDER BY count(*) DESC, po_id LIMIT 1""",
            ([r["po_id"] for r in rows],),
        )
        biggest = cur.fetchone()[0]
    chosen = [
        by_id[biggest],
        *picker.sample([r for r in rows if r["po_id"] != biggest], 9),
    ]
    chosen.sort(key=lambda r: r["po_id"])

    docs = []
    for row in chosen:
        lines = fetch(
            conn,
            """
            SELECT p.sku, p.name AS product, l.quantity_ordered, l.quantity_received,
                   l.unit_cost, l.line_total
            FROM purchase_order_lines l
            JOIN products p USING (product_id)
            WHERE l.po_id = %s
            ORDER BY p.sku
            """,
            (row["po_id"],),
        )
        doc = Doc(
            doc_id=f"invoice-{row['code'].lower()}-{row['po_id']}",
            doc_type="invoice",
            title=f"TAX INVOICE {row['po_id']} — {row['supplier']}",
            subject=f"purchase order {row['po_id']}",
            effective_from=row["received_on"],
            effective_to=row["received_on"],
            source_table="purchase_orders",
            source_key=str(row["po_id"]),
        )
        doc.blocks = [("heading", "TAX INVOICE"), ("invoice", row), ("lines", lines)]
        docs.append(doc)

    # One supplier uses a template that puts the totals block ABOVE the line
    # items, which is the layout most likely to make an extractor attach the
    # total to the wrong thing.
    docs[2].difficulty.append(TOTALS_ABOVE)
    # The page-break case goes to whichever invoice has the most lines, not to a
    # fixed index. Index 5 gave an invoice with too few rows to break a page, so
    # the manifest advertised a difficulty the artifact did not have — caught by
    # `verify_difficulty`, which is why that check exists.
    longest = max(docs, key=lambda d: len(dict(d.blocks)["lines"]))
    longest.difficulty.append(PAGE_BREAK_TABLE)
    # Two arrive as scans.
    docs[1].difficulty.append(SCANNED)
    docs[7].difficulty.extend([SCANNED, SIGNATURE])
    return docs


def build_catalogs(conn) -> list[Doc]:
    """Three price lists, each a snapshot of `supplier_prices` on a date."""
    dates = [date(2025, 4, 1), date(2025, 11, 3), date(2026, 5, 4)]
    docs = []
    for snapshot in dates:
        rows = fetch(
            conn,
            """
            SELECT s.name AS supplier, s.code, p.sku, p.name AS product,
                   c.name AS category, sp.unit_cost
            FROM supplier_prices sp
            JOIN products p USING (product_id)
            JOIN categories c USING (category_id)
            JOIN suppliers s ON s.supplier_id = sp.supplier_id
            WHERE sp.valid_period @> %s::date AND s.supplier_id = 1
            ORDER BY p.sku
            LIMIT 40
            """,
            (snapshot,),
        )
        if not rows:
            continue
        doc = Doc(
            doc_id=f"catalog-{rows[0]['code'].lower()}-{snapshot:%Y%m%d}",
            doc_type="catalog",
            title=f"PRICE LIST — {rows[0]['supplier']} — {snapshot:%B %Y}",
            subject=f"supplier {rows[0]['code']} prices",
            effective_from=snapshot,
            effective_to=None,
            source_table="supplier_prices",
            source_key=f"{rows[0]['code']}@{snapshot}",
        )
        doc.blocks = [("heading", doc.title), ("catalog", rows)]
        docs.append(doc)
    if docs:
        docs[1].difficulty.append(PAGE_BREAK_TABLE)
    return docs


POLICIES = [
    (
        "policy-returns",
        "GOODS RETURN AND CREDIT NOTE POLICY",
        date(2025, 1, 1),
        [
            (
                "1. Scope",
                "Applies to all goods received from suppliers under a "
                "current supply agreement.",
            ),
            (
                "2. Window",
                "Returns are raised within the returns window stated in "
                "the applicable supply agreement. Where no agreement is "
                "in force on the date of receipt, no return may be "
                "raised and the matter is escalated to the owner.",
            ),
            (
                "3. Condition",
                "Goods must be in original packaging and, for "
                "perishables, within one third of remaining shelf life.",
            ),
            (
                "4. Credit",
                "Credit notes are applied against the next invoice from "
                "the same supplier, never refunded in cash.",
            ),
        ],
    ),
    (
        "policy-procurement-authority",
        "PROCUREMENT AUTHORITY AND APPROVAL LIMITS",
        date(2025, 6, 15),
        [
            (
                "1. Store manager",
                "May approve a purchase order up to INR 40,000 "
                "against a supplier with terms in force.",
            ),
            (
                "2. Owner",
                "Required for any order above INR 40,000, any order "
                "against a supplier with no terms in force, and any "
                "order placed outside the agreed lead time.",
            ),
            (
                "3. Automated drafting",
                "A system may draft a purchase order. It may "
                "not place one. Every draft expires if not "
                "approved, and re-validates its prices before "
                "execution.",
            ),
        ],
    ),
    (
        "policy-cold-chain",
        "COLD CHAIN AND PERISHABLE HANDLING",
        date(2025, 9, 1),
        [
            (
                "1. Dairy",
                "Received between 2°C and 6°C. Any consignment outside "
                "that range at the point of receipt is refused entire.",
            ),
            (
                "2. Fresh produce",
                "Inspected on receipt; wastage above 5% of the "
                "consignment is raised as a return the same day.",
            ),
            (
                "3. Recording",
                "Receiving temperature is written on the delivery "
                "note and retained with the invoice.",
            ),
        ],
    ),
]


def build_policies() -> list[Doc]:
    docs = []
    for doc_id, title, effective, clauses in POLICIES:
        doc = Doc(
            doc_id=doc_id,
            doc_type="policy",
            title=title,
            subject="chain policy",
            effective_from=effective,
            effective_to=None,
            source_table="(none — free-standing)",
            source_key="",
        )
        doc.blocks = [
            ("heading", title),
            ("meta", f"Effective {effective:%d %B %Y}"),
            ("clauses", clauses),
        ]
        docs.append(doc)
    docs[2].difficulty.append(SCANNED)
    return docs


def verify_difficulty(docs: list, out: Path) -> list[str]:
    """Assert every advertised difficulty is present in the rendered artifact.

    `MANIFEST.csv` is what a reader trusts about what the pipeline was tested
    against. A row claiming `table-spans-page-break` on a single-page PDF is this
    project's recurring defect in a new costume — a check that is not running,
    wearing the label of one that is — and the first run produced exactly that.
    So every injected property is re-derived from the rendered bytes rather than
    from the intent that produced them.
    """
    import pymupdf

    failures = []
    for doc in docs:
        path = out / "sources" / SUBDIR[doc.doc_type] / doc.filename
        with pymupdf.open(path) as handle:
            pages = handle.page_count
            text = "".join(page.get_text() for page in handle)

        for mark in doc.difficulty:
            if mark == SCANNED and text.strip():
                failures.append(f"{doc.doc_id}: marked {mark} but has a text layer")
            elif mark == PAGE_BREAK_TABLE and pages < 2:
                failures.append(f"{doc.doc_id}: marked {mark} but is {pages} page")
            elif (
                mark == SIGNATURE
                and SCANNED not in doc.difficulty
                and "Authorised signatory" not in text
            ):
                failures.append(f"{doc.doc_id}: marked {mark}, no signature block")
            elif mark == BILINGUAL and not any(
                "\u0900" <= ch <= "\u097f" for ch in text
            ):
                failures.append(f"{doc.doc_id}: marked {mark} but has no Devanagari")
            elif (
                mark == TOTALS_ABOVE
                and "Subtotal (INR)" in text
                and "SKU" in text
                and text.index("Subtotal (INR)") > text.index("SKU")
            ):
                failures.append(f"{doc.doc_id}: marked {mark} but totals follow")
    return failures


def write_checksums(docs: list, out: Path) -> None:
    """`sha256sum -c` format, covering the documents and the manifest.

    `make verify-corpus` has existed since Phase 0 and skipped cleanly while this
    file was absent. It stops skipping now.
    """
    lines = [
        f"{doc.sha256}  sources/{SUBDIR[doc.doc_type]}/{doc.filename}"
        for doc in sorted(docs, key=lambda d: d.doc_id)
    ]
    manifest = (out / "MANIFEST.csv").read_bytes()
    lines.append(f"{hashlib.sha256(manifest).hexdigest()}  MANIFEST.csv")
    (out / "CHECKSUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pos"
        ),
    )
    parser.add_argument("--out", default=str(CORPUS))
    args = parser.parse_args(argv)

    import psycopg
    from corpus_render import render, write_manifest

    with psycopg.connect(args.database_url) as conn:
        docs = (
            build_contracts(conn)
            + build_invoices(conn)
            + build_catalogs(conn)
            + build_policies()
        )

    out = Path(args.out)
    for sub in SUBDIR.values():
        (out / "sources" / sub).mkdir(parents=True, exist_ok=True)

    written = set()
    for doc in docs:
        target = out / "sources" / SUBDIR[doc.doc_type] / doc.filename
        data = render(doc)
        target.write_bytes(data)
        doc.sha256 = hashlib.sha256(data).hexdigest()
        written.add(target.resolve())

    # Sweep anything this run did not write. Without it the corpus accumulates
    # documents from earlier generator versions: changing which invoices are
    # sampled left five orphans behind, absent from the manifest, and the
    # ingestion pipeline would have parsed them anyway. A directory is not a
    # manifest, and only one of the two is checked by anything.
    for stale in sorted(out.glob("sources/*/*.pdf")):
        if stale.resolve() not in written:
            stale.unlink()
            print(f"  removed stale {stale.relative_to(out)}")

    failures = verify_difficulty(docs, out)
    if failures:
        print("INJECTED DIFFICULTY NOT PRESENT IN THE RENDERED DOCUMENT:")
        for line in failures:
            print(f"  {line}")
        print("\nThe manifest would have advertised a test that does not exist.")
        return 1

    write_manifest(docs, out)
    write_checksums(docs, out)
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc.doc_type] = counts.get(doc.doc_type, 0) + 1
    hard = sum(1 for d in docs if d.difficulty)
    try:
        where = out.relative_to(REPO_ROOT)
    except ValueError:
        where = out  # --out to a temp dir, as `make corpus-verify` does
    print(f"wrote {len(docs)} documents to {where}/sources")
    for kind, n in sorted(counts.items()):
        print(f"  {kind:10} {n}")
    print(f"  {hard} carry at least one injected difficulty")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
