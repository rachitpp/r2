# ADR-0005: Evals measure, tests assert — evals stay out of CI

Date: 2026-08-05
Status: Accepted

## Context

This project produces two kinds of number: pass/fail correctness checks, and
measured accuracy figures that go in the README. The temptation is to run both
through pytest.

## Decision

They are different things and live in different places.

**Tests assert.** pytest, run in CI on every push with no API key present. Covers
pure functions (date resolution, chunk boundaries, scoring logic) and DB
integration via `CREATE DATABASE test_x TEMPLATE seeded_template` for fast
per-test isolation. `ruff check` alongside. mypy optional, does not gate.

**Evals measure.** `make eval-sql`, and `make eval-extraction` once Phase 2 builds
it — only the first exists today. Run locally at phase boundaries. They produce
numbers for the README. They are not gates.

## Alternative rejected

Evals as pytest cases, gated in CI.

## Why

1. **Quota.** A 40-question suite at 3 runs is 120 model calls. In CI that fires
   on every push and exhausts a free tier within a day.
2. **Secrets on a public repo.** Model calls in CI mean an API key in repository
   secrets on a public GitHub project. Avoidable, so avoid it.
3. **They aren't pass/fail.** 91.2% extraction accuracy is a result, not a
   failure. Forcing a threshold turns a measurement into an arbitrary gate, and
   the threshold gets tuned to whatever passes.

Use deterministic execution-match for SQL correctness — comparing result sets
costs nothing. Reserve LLM-as-judge for fuzzy retrieval questions only.

## What would flip it

Nothing while this is free-tier and public. A funded project with a private repo
could gate on evals.