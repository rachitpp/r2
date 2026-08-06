# Corpus

Real documents, published with permission. This directory is a project artifact,
not just pipeline input — a reviewer can read every source document and every
extraction the pipeline produced from it without running anything.

## Provenance and clearance

<!-- TODO Phase 2: one paragraph. Whose documents, permission to publish. -->

**PII screening:** personal records carry home addresses, phone numbers, bank
details, signatures, and ID numbers. Every document was scanned before first
commit. <!-- TODO Phase 2: what was found, what was excluded, what was redacted at source -->

## Composition

<!-- TODO Phase 2 -->

| Type | Count | Pages | Scanned | Languages |
|---|---|---|---|---|
| Contracts | | | | |
| Policies | | | | |
| Invoices | | | | |
| Catalogs | | | | |

Full per-document detail in [`MANIFEST.csv`](MANIFEST.csv).

## What's hard about them

<!-- TODO Phase 2. Be specific — this is the section people actually read.
     e.g. "9 of 41 are scanned at 200dpi with visible skew, 3 have tables
     spanning page breaks, 2 are bilingual, 4 use a supplier template that
     puts totals above line items." -->

## Extraction results

<!-- TODO Phase 2 -->

**Ground truth:** __ hand-labeled documents, stratified to over-weight scanned,
multi-page-table, and non-English cases rather than sampled randomly. Accuracy on
the easy majority tells you nothing.

    Header fields      __._%   (___/___)
    Line item F1       _.__    precision _.__  recall _.__
    Hallucination      _._%
    Miss               _._%

Reported on the stratified hard set _and_ corpus-wide, labelled as such.

**Scoring rules** — `scripts/score_extraction.py`

| Field class | Rule |
|---|---|
| Exact (invoice_number, sku, policy_id) | Binary after whitespace/case normalisation only |
| Normalised (supplier_name, description) | Case, punctuation, common abbreviations, then binary |
| Money | ±0.01 absolute. Not percentage — 1% on a large invoice hides a real error |
| Non-money numeric | Exact |
| Dates | Exact after parsing to ISO. Format variation is normalisation, not error |
| Line items | Row-level F1. A row counts only if every field in it matches |

**Partial extraction buckets.** Absent-and-null is correct, never penalised.
Absent-but-populated is a hallucination and tracked separately. Present-but-null
is a miss. Present-but-truncated is wrong, and the pattern is logged — mostly
truncations means a chunking problem, not a model problem.

## Directory layout

| Path | Contents |
|---|---|
| `sources/` | Original PDFs, unmodified |
| `parsed/` | Docling output — committed |
| `extracted/` | Raw schema-guided extraction — **never hand-edited** |
| `corrections/` | Hand-fixed deltas, one note per fix |
| `gold/` | Hand-labeled ground truth |
| `injection/` | Specimens and full traces, one directory each |

## Temporal model

Version relationships are hand-encoded in `MANIFEST.csv` (`supersedes` column)
rather than inferred — the corpus is small enough to know every one.
[`TIMELINE.md`](TIMELINE.md) is generated from it and hand-verified.

Because the document set is fixed and known upfront, every `effective_to` closes
at build time. A live system would need open-ended intervals and back-patching.

**Known edge cases:** gaps (a contract expires before its renewal is signed) must
return "no document in force", distinct from "not found".
<!-- TODO Phase 2: amendments — do they exist in this corpus? If yes, clause-level
     scoping is needed and gets its own ADR. If no, say so explicitly. -->

## Reproduction

    make ingest          # full pipeline — needs an API key
    make verify-corpus   # SHA-256 against CHECKSUMS.txt — no key
    make verify-parse    # re-run Docling on 3-doc sample, assert byte-identity
    make ingest-verify   # full re-run into temp dir, diff — local only

Pipeline pinning in [`PIPELINE.json`](PIPELINE.json).
Last full verification: <!-- TODO date + commit SHA -->

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for documented failures. It is
non-empty by design.