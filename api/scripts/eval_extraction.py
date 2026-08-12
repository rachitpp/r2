"""Score `corpus/extracted/` against the rows the documents were generated from.

**Why the database is the gold set, and what that costs.** This corpus is
synthetic: every document was rendered from a row, and `MANIFEST.csv` records
which one as `source_table` + `source_key`. So the expected values are exact,
free, and cover all 40 documents with no hand-labelling error — which is a
better instrument than 40 hand-labelled documents, not a cheaper substitute for
one.

What it cannot do is tell a model failure apart from a *document* failure. When
the generator writes `Godavari Grains &amp; Pulses` into the PDF, extraction
transcribing it faithfully scores as a miss against the database. That is not a
flaw to paper over: those divergences are precisely the entries `PLAN.md`'s
done-condition 3 wants in `corpus/corrections/`, so this scorer emits them
rather than hiding them, and two of them say the pipeline was right and the
corpus was wrong.

**No model calls.** Reads committed JSON and queries Postgres. Free to re-run,
which is what makes it usable as a check rather than a ceremony. It needs a
database and therefore never runs in CI (ADR-0005).

The four numbers match the README block exactly:

    header fields   scalar fields per document, exact match
    line item F1    invoice lines and catalog prices, matched on identity
    hallucination   values or rows present in the extraction, absent in gold
    miss            values or rows present in gold, absent from the extraction

Hallucination and miss are reported separately on purpose. An agent that will
act on this data is harmed differently by an invented supplier price than by a
missing one: the first is acted on, the second is noticed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "corpus"

# Scalar fields compared per document type. The key is the extracted field; the
# value is the gold key produced by the loaders below.
HEADER_FIELDS = {
    "contract": [
        "supplier_code",
        "effective_from",
        "effective_to",
        "payment_terms_days",
        "lead_time_days",
        "min_order_value",
        "volume_discount_pct",
        "returns_window_days",
    ],
    "invoice": ["supplier_code", "subtotal"],
    # NOT supplier_code. No catalog prints one — measured, all three have zero
    # occurrences of `SUP-` in their text. Scoring it meant two of the three
    # scored CORRECT for inferring `SUP-01` from the supplier name, and the one
    # that honestly returned null scored as a miss. **The metric was rewarding
    # the hallucination and penalising the refusal**, which is the opposite of
    # what this project is built to measure. See KNOWN_ISSUES entry 12.
    "catalog": ["effective_from"],
}

# Documents that restate only some of their clauses. `supplier_terms` is a wide
# table that supersedes as a set, so its row carries the inherited full set while
# the document deliberately states three clauses and nothing else — a gold set
# derived from that row therefore CANNOT score these, and marking the unstated
# clauses as misses measures the inheritance rather than the extraction. This is
# exactly the case the clause-level provenance decision exists for, and it needs
# `supplier_term_clauses` (Phase 3) to score properly.
AMENDMENTS = {"contract-sup-04-20251018", "contract-sup-09-20250909"}

# Policies are free-standing — no row was behind them, so there is nothing to
# score against and pretending otherwise would invent a denominator.
UNSCORED_TYPES = {"policy"}

MONEY_TOLERANCE = Decimal("0.005")


@dataclass
class Tally:
    """Counts, kept separately so a rate can never be printed without its
    denominator. The Phase 1 eval learned this the expensive way."""

    correct: int = 0
    total: int = 0
    hallucinated: int = 0
    missed: int = 0
    unscorable: int = 0
    divergences: list[dict] = field(default_factory=list)

    def rate(self) -> float | None:
        return None if self.total == 0 else 100.0 * self.correct / self.total


def _num(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def equal(extracted: object, gold: object) -> bool:
    """Exact match, with a cent of tolerance on money.

    Deliberately not fuzzy on text: `Godavari Grains &amp; Pulses` must not
    quietly compare equal to `Godavari Grains & Pulses`. That divergence is a
    finding, and a lenient comparison is how findings get lost.
    """
    a, b = _num(extracted), _num(gold)
    if a is not None and b is not None:
        return abs(a - b) <= MONEY_TOLERANCE
    if extracted is None or gold is None:
        return extracted is None and gold is None
    return str(extracted).strip() == str(gold).strip()


def load_manifest(corpus: Path) -> list[dict]:
    with (corpus / "MANIFEST.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def gold_from_database(rows: list[dict], dsn: str) -> dict[str, dict]:
    """Build expected values by reading back the rows the documents came from."""
    import psycopg

    gold: dict[str, dict] = {}
    with psycopg.connect(dsn, connect_timeout=30) as conn, conn.cursor() as cur:
        for row in rows:
            doc_id, doc_type, key = row["doc_id"], row["doc_type"], row["source_key"]
            if doc_type in UNSCORED_TYPES or not key:
                continue

            if doc_type == "contract":
                cur.execute(
                    """select s.code, t.effective_from, t.effective_to,
                              t.payment_terms_days, t.lead_time_days,
                              t.min_order_value, t.volume_discount_pct,
                              t.returns_window_days
                       from supplier_terms t join suppliers s using (supplier_id)
                       where t.supplier_terms_id = %s""",
                    (int(key),),
                )
                got = cur.fetchone()
                if not got:
                    continue
                gold[doc_id] = {
                    "type": doc_type,
                    "header": dict(zip(HEADER_FIELDS["contract"], got, strict=True)),
                    "rows": [],
                }

            elif doc_type == "invoice":
                cur.execute(
                    """select s.code, o.subtotal from purchase_orders o
                       join suppliers s using (supplier_id) where o.po_id = %s""",
                    (int(key),),
                )
                got = cur.fetchone()
                if not got:
                    continue
                cur.execute(
                    """select p.name, l.quantity_ordered, l.unit_cost, l.line_total
                       from purchase_order_lines l join products p using (product_id)
                       where l.po_id = %s order by p.name""",
                    (int(key),),
                )
                gold[doc_id] = {
                    "type": doc_type,
                    "header": dict(zip(HEADER_FIELDS["invoice"], got, strict=True)),
                    "rows": [
                        {
                            "key": r[0],
                            "quantity": r[1],
                            "unit_price": r[2],
                            "line_total": r[3],
                        }
                        for r in cur.fetchall()
                    ],
                }

            elif doc_type == "catalog":
                code, _, on = key.partition("@")
                cur.execute(
                    """select p.sku, p.name, sp.unit_cost
                       from supplier_prices sp
                       join products p using (product_id)
                       join suppliers s using (supplier_id)
                       where s.code = %s and sp.valid_period @> %s::date
                       order by p.sku""",
                    (code, on),
                )
                priced = cur.fetchall()
                gold[doc_id] = {
                    "type": doc_type,
                    "header": {"supplier_code": code, "effective_from": on},
                    "rows": [
                        {"key": r[0], "product_name": r[1], "unit_price": r[2]}
                        for r in priced
                    ],
                }
    return gold


def row_identity(doc_type: str, row: dict) -> str | None:
    """What names a row. Catalogs carry an explicit product code; invoice lines
    do not, so they are matched on their line total, which the generator derives
    from quantity x unit cost and is therefore unique per line in practice."""
    if doc_type == "catalog":
        return str(row.get("product_code") or row.get("key") or "").strip() or None
    value = _num(row.get("line_total"))
    return None if value is None else f"{value:.2f}"


def flatten(doc_type: str, extracted: dict) -> dict:
    """Put a contract's clauses where the header comparison can see them.

    A contract does not carry `payment_terms_days` at the top level — it carries
    a `clauses` list of {clause, value, verbatim}, which is the clause-level
    provenance decision working as intended. The first version of this scorer
    read the top level anyway and reported **42.2% header accuracy against an
    extraction that was very nearly perfect**, because every clause read as
    `None`. A confident number measuring the wrong field is the defect this
    repo keeps finding, and this scorer produced one on its first run.
    """
    if doc_type != "contract":
        return extracted
    flat = dict(extracted)
    for clause in extracted.get("clauses") or []:
        if isinstance(clause, dict) and clause.get("clause"):
            flat.setdefault(clause["clause"], clause.get("value"))
    return flat


def score_document(
    doc_type: str, extracted: dict, gold: dict, tally: Tally, doc_id: str = ""
) -> None:
    extracted = flatten(doc_type, extracted)
    if doc_id in AMENDMENTS:
        tally.unscorable += 1
        return
    for field_name in HEADER_FIELDS.get(doc_type, []):
        if field_name not in gold["header"]:
            continue
        want = gold["header"][field_name]
        got = extracted.get(field_name)
        if field_name in {"effective_from", "effective_to"} and want is not None:
            want = str(want)
        if doc_type == "catalog" and field_name == "effective_from":
            # The document prints a MONTH — "PRICE LIST - ... - November 2025".
            # The manifest key carries the day the prices were selected on, which
            # was never printed anywhere. Demanding it scored the model wrong for
            # reading its own document correctly, so this compares what the
            # document actually states.
            want = str(want)[:7] if want else want
            got = str(got)[:7] if got else got
        tally.total += 1
        if equal(got, want):
            tally.correct += 1
        elif got is None:
            tally.missed += 1
            tally.divergences.append(
                {"doc": doc_id, "field": field_name, "gold": want, "got": None}
            )
        else:
            tally.hallucinated += 1
            tally.divergences.append(
                {"doc": doc_id, "field": field_name, "gold": want, "got": got}
            )


def score_rows(doc_type: str, extracted: dict, gold: dict, tally: Tally) -> None:
    key_field = "prices" if doc_type == "catalog" else "line_items"
    got_rows = extracted.get(key_field) or []
    want = {row["key"]: row for row in gold["rows"]}

    seen: set[str] = set()
    for row in got_rows:
        ident = row_identity(doc_type, row)
        match = None
        if doc_type == "catalog":
            match = want.get(ident)
        else:
            for k, candidate in want.items():
                if k in seen:
                    continue
                if equal(row.get("line_total"), candidate["line_total"]) and equal(
                    row.get("quantity"), candidate["quantity"]
                ):
                    match, ident = candidate, k
                    break
        tally.total += 1
        if match is None:
            tally.hallucinated += 1
            continue
        price_ok = equal(row.get("unit_price"), match["unit_price"])
        if price_ok:
            tally.correct += 1
            seen.add(ident)
        else:
            tally.hallucinated += 1

    for k in want:
        if k not in seen:
            tally.missed += 1
            tally.total += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--gold-out", default=None, help="write the derived gold set")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    corpus = Path(args.corpus)
    extracted_dir = corpus / "extracted"
    if not extracted_dir.is_dir():
        print("corpus/extracted/ does not exist — run `make extract` first.")
        return 1
    if not args.database_url:
        print("DATABASE_URL is not set. The gold set is read from the rows the")
        print("documents were generated from; there is nothing to score without it.")
        return 1

    manifest = load_manifest(corpus)
    gold = gold_from_database(manifest, args.database_url)

    header, rows = Tally(), Tally()
    per_doc: list[dict] = []
    for entry in manifest:
        doc_id, doc_type = entry["doc_id"], entry["doc_type"]
        if doc_id not in gold:
            continue
        path = extracted_dir / f"{doc_id}.json"
        if not path.is_file():
            print(f"  MISSING {doc_id} — no extraction on disk")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))

        before = (header.correct, header.total, rows.correct, rows.total)
        score_document(doc_type, data, gold[doc_id], header, doc_id)
        score_rows(doc_type, data, gold[doc_id], rows)
        per_doc.append(
            {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "header_correct": header.correct - before[0],
                "header_total": header.total - before[1],
                "row_correct": rows.correct - before[2],
                "row_total": rows.total - before[3],
            }
        )

    matched = rows.correct
    precision = matched / (matched + rows.hallucinated) if matched else 0.0
    recall = matched / (matched + rows.missed) if matched else 0.0
    f1 = (
        0.0
        if not (precision + recall)
        else 2 * precision * recall / (precision + recall)
    )
    scored_docs = len(per_doc)

    print(
        f"scored     {scored_docs} documents ({len(manifest) - scored_docs} unscored)"
    )
    print(
        f"gold       the rows in {args.database_url.rsplit('/', 1)[-1].split('?')[0]}"
    )
    print()
    print(f"  header fields    {header.rate():.1f}%  ({header.correct}/{header.total})")
    if header.unscorable:
        print(
            f"                   {header.unscorable} clause-level amendments not"
            " scored — see AMENDMENTS in this file"
        )
    print(
        f"  line item F1     {f1:.2f}   ({matched} rows across {scored_docs} documents)"
    )
    hall = 100.0 * rows.hallucinated / rows.total if rows.total else 0.0
    miss = 100.0 * rows.missed / rows.total if rows.total else 0.0
    print(f"  hallucination    {hall:.1f}%  ({rows.hallucinated}/{rows.total})")
    print(f"  miss             {miss:.1f}%  ({rows.missed}/{rows.total})")

    if header.divergences:
        print()
        print(f"{len(header.divergences)} header divergences — each needs a note in")
        print(
            "corpus/corrections/ saying which side was wrong (PLAN done-condition 3):"
        )
        for d in header.divergences[:20]:
            print(
                f"  {d['doc']:<30} {d['field']:<20} "
                f"gold={d['gold']!r}  got={d['got']!r}"
            )

    if args.gold_out:
        Path(args.gold_out).write_text(
            json.dumps(gold, indent=2, default=str, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\nwrote {args.gold_out}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "documents_scored": scored_docs,
                    "header": {"correct": header.correct, "total": header.total},
                    "rows": {
                        "matched": matched,
                        "total": rows.total,
                        "hallucinated": rows.hallucinated,
                        "missed": rows.missed,
                        "f1": round(f1, 4),
                    },
                    "per_document": per_doc,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
