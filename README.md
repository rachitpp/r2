# POS Copilot

A retail POS database with a natural-language query interface, and a procurement
agent that drafts purchase orders into a human approval queue.

<!-- TODO Phase 5: GIF of demo beat 3 — draft PO → approval card → approve → audit entry -->
<!-- TODO Phase 5: link unlisted YouTube video -->

Portfolio project, not a production system. Built solo, free tier only.

## What's actually interesting here

Most RAG portfolio projects show a chatbot answering questions over documents.
Three things here are harder and are measured rather than claimed:

- **Temporal correctness.** Supplier terms change. Ask what the payment terms are
  and you get today's answer; ask what they were before the renegotiation and you
  get the correct historical clause. Every chunk and every extracted term carries
  `effective_from` / `effective_to`.
- **A real approval queue.** The agent drafts purchase orders; it does not place
  them. Proposals persist as database rows, survive a server restart, expire, and
  re-validate their inputs before executing — a proposal drafted against a price
  that has since moved refuses to fire.
- **Prompt injection, demonstrated rather than asserted.** The corpus contains
  labelled injection specimens with committed traces showing a naive
  implementation following them and this one not. See [`corpus/injection/`](corpus/injection/).

## Results

Measured, not estimated. Methodology in [`corpus/README.md`](corpus/README.md).

**Extraction** _(n=__ hand-labeled documents)_
<!-- TODO Phase 2 -->

    Header fields      __._%   (___/___)
    Line item F1       _.__    (___ rows across __ documents)
    Hallucination      _._%    (___/___)
    Miss               _._%    (___/___)

**Text-to-SQL** _(n=49 questions × 3 runs = 147 responses, 2026-08-08, prompt
`f3b7a9193a56f10d`, `gemini-3.6-flash` via Vertex, ~$3.32)_

    Execution accuracy      91.4%  (96/105 not-view-covered, 95% CI 84.5-95.4%)
                            100%   (33/33 view-covered)
                            93.5%  (129/138 overall, 95% CI 88.1-96.5%)
    Silent-wrong            3 questions of 49 (q017, q026, q049)
    Cross-run variance      2.0%   (1 question of 49 changed outcome)
    Median attempts         not measured — no retry loop exists

Read the interval, not the point estimate: 84.5–95.4% **straddles** the 85% line
this project set for itself, so the headline supports "measure again", not "good
enough". Every number here is scored by deterministic result-set comparison — no
LLM-as-judge.

**One of those three silent-wrongs is a defect in the question, found after the
run.** q049's reference returns one row of two columns; the model returned the
same two numbers as two labelled rows, rounded to 2dp instead of 1dp, and was
scored wrong three times for it. Withdrawing it gives 94.1% (96/102, CI
87.8–97.3%), which clears 85% — one under-determined question out of 35 moved the
interval across the decision line, which is the most useful thing in this block.
It is reported this way rather than silently corrected, and the replacement
question is measured in the next run, not this one.

**The cross-run variance figure is the least trustworthy number in this block, and
measuring it four times is how that was established.** A strict replication — same
prompt, same 47 questions, fresh runs 3–5, nothing replayed — returned **4.3%**
where the first triple returned **10.6%**:

| sample | prompt | not-view-covered | variance |
|---|---|---|---|
| first triple (runs 0–2) | `415953…` | 88.9% (88/99) | 10.6% |
| **strict replication (runs 3–5)** | `415953…` | 93.9% (93/99) | **4.3%** |
| pooled (runs 0–5) | `415953…` | 91.9% (182/198) | 12.8% |
| current (runs 0–2) | `f3b7a9…` | 91.4% (96/105) | 2.0% |

Two triples of the identical prompt over the identical questions, a factor of 2.5
apart, with the project's own 10% decision line sitting between them. The metric is
also monotone in the number of runs — it counts questions whose outcome ever
differed — so pooling six runs reads *higher* by construction, not because the
system got less stable. A threshold stated as "variance > 10%" measures the
sampling budget as much as the model, which is why the decision it was built to
support now rests on accuracy instead. Reasoning and what should replace it:
[`docs/adr/0001-text-to-sql-vs-query-catalog.md`](docs/adr/0001-text-to-sql-vs-query-catalog.md).

Two more things one triple could not have shown. **q017 is not a model failure:**
across six runs of the same prompt it is wrong three times and right three times,
writing `HAVING count(*) FILTER (late) > 0` when it fails and
`HAVING avg(actual) > avg(contracted)` when it passes — two defensible readings of
a question that never said which. **And the 100% on view-covered questions was an
artifact:** one of them fails once in six runs, so the honest figure is 65/66.

Hallucination rate matters more than headline accuracy. A pipeline at 85% with
zero hallucinations beats one at 92% with 5%, because the second lies confidently
to an agent that will act on it.

**Injection specimens:** __ of __ held. Failures are documented rather than
omitted.

## Run it

Three levels, by how much setup you want.

**1. Read only — no setup.** Browse [`corpus/`](corpus/) for the source documents
and every extraction the pipeline produced, [`corpus/injection/`](corpus/injection/)
for the attack traces, and [`docs/adr/`](docs/adr/) for why things are the way
they are.

**2. Run the demo — no API key.**

    cp .env.example .env
    docker compose up

Opens on `localhost:3000` in demo mode: real UI, real data, replayed agent runs.
Cached trajectories load through the same code path that would call a model.

**3. Run live — your own free-tier key.** Add a key to `.env`, set
`DEMO_MODE=false`, and `docker compose up`. Optionally
`docker compose --profile local-models up` to run generation locally via Ollama.

No hosted instance. A public chat endpoint over this corpus would be an
open-ended query interface into personal documents, and free-tier limits mean two
simultaneous visitors get an error.

## How it works

    web/ (Next.js)  ──JSON + SSE──▶  api/ (FastAPI)
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                   generated SQL    pgvector          agent loop
                   (read-only role,  retrieval        (≤6 tool calls)
                    enforced LIMIT)  (date + role             │
                          │           pre-filtered)           ▼
                          └───────────────┼──────────  proposed_actions
                                          ▼            (expiry, spending cap,
                              Postgres 16 + pgvector     stale re-validation)
                                          │                   │
                                          ▼                   ▼
                                    seeded POS data      audit log

The agent never runs inside a request handler. `POST /runs` returns immediately;
a worker claims the row with `SELECT ... FOR UPDATE SKIP LOCKED`; the UI
subscribes over SSE. That's what makes "survives a restart" true rather than
aspirational.

## Design decisions

Full set in [`docs/adr/`](docs/adr/). Three worth reading:

- **[ADR-0001](docs/adr/0001-text-to-sql-vs-query-catalog.md)** — why generated
  SQL over a curated query catalog, including an audit that found the benchmark
  evidence for the opposite conclusion came from vendors with a stake in it and
  was drawn from a schema roughly 50x larger than this one. The switch is
  governed by four measured thresholds, not by argument.
- **[ADR-0002](docs/adr/0002-procurement-as-flagship.md)** — why procurement
  rather than fraud detection, and the constraint that would bind if anomaly
  detection is ever built: the agent reports patterns, never people.
- **[ADR-0006](docs/adr/0006-determinism-scoped-to-parse-layer.md)** — why the
  reproducibility claim is scoped to the parse layer instead of the whole
  pipeline.

The highest-leverage artifact in the repo is
[`api/prompts/context/business_context.md`](api/prompts/context/business_context.md).
A peer-reviewed study found GPT-4 at 8.3% text-to-SQL accuracy with schema alone
versus 78.3% with a business-context document — and that narrowing the schema
without one only got failure down to 50%. Context does the work.

## Corpus

Real documents, published with permission. Personal records screened for PII
before first commit. Composition, what makes them hard, and known extraction
failures are in [`corpus/README.md`](corpus/README.md) —
[`KNOWN_ISSUES.md`](corpus/KNOWN_ISSUES.md) is deliberately non-empty.

Raw pipeline output in [`corpus/extracted/`](corpus/extracted/) is never
hand-edited. Hand fixes live in [`corpus/corrections/`](corpus/corrections/) with
a note per fix saying what the pipeline got wrong. That separation is what makes
the accuracy number above believable.

## Reproducibility

- **Parse layer:** byte-identical, asserted in CI on a committed 3-document sample.
- **Artifact integrity:** SHA-256 verified against `corpus/CHECKSUMS.txt` on every push.
- **Extraction layer:** pinned model and temperature 0; verified reproducible
  <!-- TODO date --> via `make ingest-verify`.

LLM inference is not guaranteed byte-stable across provider changes. The claim is
scoped accordingly rather than overstated.

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI, JSON + SSE | Shares Pydantic models with agent tool schemas |
| Frontend | Next.js (App Router) + Tailwind, TS | — |
| Async work | Postgres worker, `SKIP LOCKED` | Runs survive restarts; no broker needed |
| Database | Postgres 16 + pgvector | One store for business data, vectors, agent state |
| Migrations | Numbered SQL, applied in order | No production DB to evolve; readable in one file |
| Parsing | Docling, self-hosted, pinned | Deterministic, local, no per-page cost |
| Extraction | Schema-guided LLM → Pydantic | Structure enforced at decode time |
| Embeddings | bge-small-en-v1.5, local CPU | No quota, no rate limit, sufficient at this size |
| Generation | Role config: `PLAN`/`EXTRACT`/`CLASSIFY` | Local vs. API is config, not a refactor |
| Agent | Custom loop, state in Postgres | Explicit call budgeting under free-tier limits |
| Tracing | Langfuse, self-hosted | Optional; no-op when unconfigured |
| Tests | pytest + ruff | Evals are separate — they measure, not assert |
| Deps | uv + npm, lockfiles committed | Full transitive pinning |

## Status

<!-- TODO: keep current -->
**Phase 0 complete — data foundation.** Postgres schema with temporal supplier
terms and prices, a stock-simulating seed generator, and a read-only role.
`make db` builds a seeded database; `make reset` rebuilds it in about a second
from a template. Seed output is byte-identical on re-run, asserted in CI at both
sizes with no API key.

Phase 1 (structured Q&A, eval harness, first UI) is next. See
[`docs/PLAN.md`](docs/PLAN.md).