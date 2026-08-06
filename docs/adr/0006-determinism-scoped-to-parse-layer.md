# ADR-0006: Determinism asserted at the parse layer; extraction claimed honestly

Date: 2026-08-05
Status: Accepted

## Context

The corpus is fixed, public, and committed, so `make ingest` should be
reproducible and that reproducibility should be verifiable by a reviewer. The
naive version — run `make ingest` twice in CI and diff — cannot work: it requires
model calls, meaning quota consumption and an API key in secrets on a public repo.

## Decision

Split the claim by layer.

**In CI, every push, no secrets required:**
- `make verify-corpus` — SHA-256 every file in `parsed/` and `extracted/` against
  `corpus/CHECKSUMS.txt`. Catches partial commits, accidental edits, corruption.
- `make verify-parse` — actually re-run Docling on a committed 3-document sample
  and assert byte-identity. Docling is local with no network calls, so this is a
  real reproducibility assertion that costs nothing and needs no key.

**Local, gated, before tagging:**
- `make ingest-verify` — re-run the full pipeline into a temp directory and diff.
  Record the last-verified date and commit SHA in the corpus README.

Pin the Docling version, model string, and temperature in `corpus/PIPELINE.json`.

## The honest claim

**LLM extraction at temperature 0 is not guaranteed byte-identical across runs.**
Providers do not promise it; batching and hardware nondeterminism break it, and a
model string can be silently updated underneath you.

So the README says:

> Deterministic parse layer, asserted in CI. Extraction layer verified
> reproducible as of 2026-08-05 with pinned model and temperature 0. LLM inference
> is not guaranteed byte-stable across provider changes.

Not "fully deterministic pipeline."

## Alternative rejected

Claiming end-to-end determinism, or running full ingestion in CI.

## Why

Overclaiming and having a reviewer catch it costs more than the honest version
gains. A scoped claim that is actually true and actually asserted is a stronger
artifact than a broad one that isn't.

## What would flip it

A provider offering a genuine determinism guarantee, or moving extraction to a
pinned local model where byte-stability can be asserted directly. The latter is
plausible at the 16GB RAM tier and would be worth revisiting.