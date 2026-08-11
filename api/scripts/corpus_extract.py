#!/usr/bin/env python3
"""Schema-guided extraction over the parsed corpus.

Reads `corpus/parsed/*.md`, sends each document through the EXTRACT role with
`api/prompts/extract.md`, and writes the raw response to
`corpus/extracted/<doc_id>.json` plus a report to `corpus/EXTRACT.csv`.

**This is the step that spends.** 40 documents is 40 calls, roughly $0.80 at the
rate the Phase 1 measurement ran at. It carries a call ceiling and a spend
ceiling like every other runner (CLAUDE.md rule 2), the responses are cached
permanently so a re-score costs nothing, and `--provider stub` exercises every
line of it with no key and no network.

**Raw output, never repaired.** `corpus/extracted/` is pipeline output and is
never hand-edited (rule 8) — fixes belong in `corpus/corrections/` with a note
saying what the pipeline got wrong. A response that is not JSON at all is
written out as it arrived and recorded as invalid, because the pipeline failing
in the open is a result and a swallowed failure is not.

**No byte-identity claim here, deliberately.** ADR-0006 scopes determinism to the
parse layer precisely because the model layer has none, and there are no sampling
parameters left to pin. Reproducibility at this layer is measured by re-running
and diffing, not asserted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pos_copilot import extract as extract_mod
from pos_copilot.model import (
    Budget,
    BudgetExceeded,
    Pacer,
    ResponseCache,
    StubProvider,
    resolve_provider,
)
from pos_copilot.prompts import bundle_fingerprint, load_extract_prompt

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "corpus"
CACHE_DIR = CORPUS / ".cache"

REPORT_FIELDS = [
    "doc_id",
    "doc_type",
    "injected_difficulty",
    "valid",
    "readable",
    "n_records",
    "reconciles",
    "n_errors",
    "errors",
    "response_sha256",
]


def load_manifest(corpus: Path) -> list[dict]:
    with (corpus / "MANIFEST.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def record_count(doc_type: str, data: dict | None) -> int:
    """How many rows the extraction found, by the name each type calls them."""
    if not data:
        return 0
    key = {
        "contract": "clauses",
        "invoice": "line_items",
        "catalog": "prices",
        "policy": "rules",
    }[doc_type]
    rows = data.get(key)
    return len(rows) if isinstance(rows, list) else 0


def build_stub(docs: list[dict], parsed: Path) -> StubProvider:
    """A schema-valid answer per document, keyed on the id in its prompt.

    It is not pretending to extract anything — it returns a fixed shape so the
    runner's plumbing can be exercised end to end with no key. Whether the values
    are right is the gold set's question, and asking it of a stub would be
    measuring the stub (ADR-0005).

    One document deliberately returns unparseable text, because the invalid path
    writes a file, records an error and keeps going, and a runner whose failure
    branch has never executed is a runner with an untested failure branch.
    """
    responses: dict[str, str] = {}
    for index, doc in enumerate(docs):
        doc_id, doc_type = doc["doc_id"], doc["doc_type"]
        if index == 0:
            responses[f"Identifier: {doc_id}\n"] = "I could not read that document."
            continue
        body: dict = {"readable": True}
        if doc_type == "contract":
            body |= {
                "supplier_code": doc["source_key"],
                "supplier_name": "Stub Supplier",
                "document_kind": "agreement",
                "effective_from": doc["effective_from"] or "2025-01-01",
                "effective_to": doc["effective_to"] or None,
                "clauses": [
                    {
                        "clause": "payment_terms_days",
                        "clause_number": "3",
                        "value": 30,
                        "verbatim": "Net 30 days from invoice date.",
                    }
                ],
            }
        elif doc_type == "invoice":
            body |= {
                "invoice_number": doc_id.rsplit("-", 1)[-1],
                "supplier_code": "SUP-01",
                "supplier_name": "Stub Supplier",
                "invoice_date": doc["effective_from"] or "2025-01-01",
                "purchase_order_ref": None,
                "currency": "INR",
                "subtotal": 100.0,
                "tax_total": 5.0,
                "total": 105.0,
                "line_items": [
                    {
                        "description": "Stub line",
                        "quantity": 2,
                        "unit_price": 50.0,
                        "line_total": 100.0,
                    }
                ],
            }
        elif doc_type == "catalog":
            body |= {
                "supplier_code": "SUP-01",
                "supplier_name": "Stub Supplier",
                "effective_from": doc["effective_from"] or "2025-01-01",
                "currency": "INR",
                "prices": [
                    {
                        "product_name": "Stub product",
                        "product_code": None,
                        "unit_price": 45.5,
                        "case_pack": 12,
                    }
                ],
            }
        else:
            body |= {
                "policy_name": doc["title"] or doc_id,
                "effective_from": doc["effective_from"] or None,
                "rules": [{"heading": "Stub", "statement": "A stub rule."}],
            }
        # Keyed on the identifier line, which appears in the rendered prompt and
        # nowhere else, so one document's answer cannot match another's prompt.
        responses[f"Identifier: {doc_id}\n"] = json.dumps(body, indent=2)
    return StubProvider(responses=responses, default='{"readable": false}')


def run(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    out = Path(args.out) if args.out else corpus / "extracted"
    parsed = corpus / "parsed"
    if not parsed.is_dir():
        print(f"no parsed corpus at {parsed} — run `make ingest` first")
        return 1

    # Refused up front, not gated later. The report guard below stops a stub run
    # publishing EXTRACT.csv, but the per-document writes are unconditional — so
    # without this a plumbing run would leave 40 files of invented values sitting
    # in a committed directory, each one looking exactly like a real extraction.
    # Nothing downstream could tell them apart, which is the whole failure.
    if args.provider == "stub" and out.resolve() == (corpus / "extracted").resolve():
        print(
            "refusing: --provider stub returns invented values, and this would "
            "write them into corpus/extracted/.\nPass --out <dir> for a plumbing "
            "run — `make extract-stub` does."
        )
        return 1

    docs = load_manifest(corpus)
    if args.only:
        wanted = set(args.only.split(","))
        docs = [d for d in docs if d["doc_id"] in wanted]
    if args.limit:
        docs = docs[: args.limit]
    if not docs:
        print("no documents selected")
        return 1

    bundle = load_extract_prompt()
    fingerprint = bundle_fingerprint(bundle.hashes)

    if args.provider == "stub":
        provider = build_stub(load_manifest(corpus), parsed)
        cache = ResponseCache(root=CACHE_DIR, enabled=False)
    else:
        provider = resolve_provider("EXTRACT")
        cache = ResponseCache(root=CACHE_DIR, enabled=not args.no_cache)

    print(f"provider   {provider.name} / {provider.model}")
    print(f"prompt     {fingerprint}")
    print(f"documents  {len(docs)}")
    if args.provider != "stub":
        pacer = getattr(provider, "pacer", Pacer())
        print(f"pacing     {pacer.rpm} rpm -> {pacer.min_interval:.1f}s between starts")
        print(f"ceiling    {args.max_calls} calls / ${args.max_spend:.2f}")
    print()

    out.mkdir(parents=True, exist_ok=True)
    budget = Budget(max_calls=args.max_calls, max_spend_usd=args.max_spend)
    report: list[dict] = []
    written: set[Path] = set()
    stopped = False

    for doc in docs:
        doc_id, doc_type = doc["doc_id"], doc["doc_type"]
        markdown = (parsed / f"{doc_id}.md").read_text(encoding="utf-8")
        prompt = bundle.render(
            doc_type=doc_type,
            doc_id=doc_id,
            json_schema=extract_mod.SCHEMAS[doc_type],
            document=markdown,
        )

        # The document text is the cache's staleness key: re-parsing a document
        # changes what the model would be sent, and an answer to the old text
        # judged against the new one is the hole `question_sha` closed for the
        # eval cache. Same mechanism, same reason.
        raw = cache.get(fingerprint, doc_id, 0, markdown)
        if raw is None:
            try:
                budget.check(prompt)
            except BudgetExceeded as exc:
                print(f"\n{exc}")
                stopped = True
                break
            raw = provider.generate(prompt)
            budget.record(prompt)
            cache.put(fingerprint, doc_id, 0, raw, markdown)

        result = extract_mod.parse(doc_id, doc_type, raw)
        target = out / f"{doc_id}.json"
        target.write_text(
            extract_mod.strip_json_fences(raw) + "\n", encoding="utf-8", newline="\n"
        )
        written.add(target.resolve())

        rec = None
        if doc_type == "invoice" and result.data:
            rec = extract_mod.reconciles(result.data)

        report.append(
            {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "injected_difficulty": doc["injected_difficulty"],
                "valid": result.ok,
                "readable": bool(result.data and result.data.get("readable")),
                "n_records": record_count(doc_type, result.data),
                "reconciles": "" if rec is None else rec,
                "n_errors": len(result.errors),
                "errors": " | ".join(result.errors),
                "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            }
        )
        mark = "ok " if result.ok else "BAD"
        print(
            f"  {mark} {doc_id:34} {record_count(doc_type, result.data):3} records"
            + (f"  {len(result.errors)} errors" if result.errors else "")
        )
        for message in result.errors[:3]:
            print(f"        {message}")

    # Same rule the parse step learned: only a whole-corpus run into the
    # canonical location may write the report, or a --only run leaves a report
    # claiming the corpus is one document. See corpus_ingest.is_canonical.
    #
    # And the stub is never canonical, whatever it is pointed at. Its answers are
    # a fixed shape with invented values; letting them reach corpus/EXTRACT.csv
    # would publish a results table that measured nothing, which is this
    # project's defect class with a number attached to it.
    canonical = (
        args.provider != "stub"
        and not args.only
        and not args.limit
        and not stopped
        and out.resolve() == (corpus / "extracted").resolve()
    )
    if canonical:
        for stale in sorted(out.glob("*.json")):
            if stale.resolve() not in written:
                stale.unlink()
                print(f"  removed stale {stale.name}")
        with (corpus / "EXTRACT.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=REPORT_FIELDS, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(sorted(report, key=lambda r: r["doc_id"]))

    valid = sum(1 for r in report if r["valid"])
    print(f"\n{valid}/{len(report)} well-formed")
    if args.provider != "stub":
        print(f"{budget.calls} calls, ~${budget.spend_usd:.2f} estimated")
        print(f"cache      {cache.hits} hits, {cache.misses} misses")
    if canonical:
        print("wrote corpus/extracted/ and corpus/EXTRACT.csv")
    else:
        print(f"wrote {out} — partial run, EXTRACT.csv left alone")

    bad = [r for r in report if not r["valid"]]
    if bad:
        print(f"\n{len(bad)} documents did not validate:")
        for row in bad:
            print(f"  {row['doc_id']} — {row['errors'][:120]}")
    return 1 if stopped else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("vertex", "stub"), default="vertex")
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--out", default=None, help="defaults to <corpus>/extracted")
    parser.add_argument("--only", default="", help="comma-separated doc ids")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-cache", action="store_true")
    # 60 and $2.00 against a 40-document corpus: enough headroom for a retry,
    # not enough to fund a runaway. Raise it deliberately, not reflexively.
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--max-spend", type=float, default=2.00)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
