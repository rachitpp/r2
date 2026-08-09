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

**Text-to-SQL** _(n=49 questions × 3 runs = 147 responses, 2026-08-09, prompt
`f3b7a9193a56f10d`, `gemini-3.6-flash` via Vertex, ~$3.32)_

    Execution accuracy      91.4%  (96/105 not-view-covered, 95% CI 85-95%)
                            97.0%  (32/33 view-covered)
                            92.8%  (128/138 overall, 95% CI 87-96%)
    Silent-wrong            5 questions of 49 (q011, q026, q034, q043, q047)
    Execution errors        2 questions (q026, q050) — statement timeouts
    Cross-run variance      12.2%  (6 questions changed outcome across 3 runs)
    Median attempts         not measured — no retry loop exists

Read the interval, not the point estimate: 85–95% sits **on** the 85% line this
project set for itself, so the headline supports "measure again", not "good
enough". Every number is scored by deterministic result-set comparison — no
LLM-as-judge.

**Not one of those five silent-wrongs is a stable failure.** Every one is correct
in at least one of the three runs, and four of the five were correct three times
out of three in the previous triple. The failure mode this project is built to
find is not "the model cannot do this" — it is "the model does this correctly
most of the time", which is harder to catch and worse to ship.

**This block previously read 97.1% with zero silent-wrongs, and that number was
wrong in an instructive way.** After fixing three questions whose references were
under-determined, only those three were re-measured — so failures got a second
draw and successes did not. A clean triple over the identical set came back 5.7
points lower, with variance at 12.2% rather than 0.0%, and the instability turned
out to be in the questions that had *not* been re-rolled. Re-measuring only what
failed is the cheapest way to publish a wrong number, and it looks like diligence
while you do it.

**The cross-run variance figure is the least trustworthy number in this block, and
measuring it five times is how that was established.** Every row below is the same
system, scored the same way:

| sample | prompt | questions | not-view-covered | variance |
|---|---|---|---|---|
| first triple (0–2) | `415953…` | 47 | 88.9% (88/99) | 10.6% |
| **strict replication (3–5)** | `415953…` | 47 | 93.9% (93/99) | **4.3%** |
| _pooled, not a triple (0–5)_ | `415953…` | 47 | 91.9% (182/198) | _12.8%_ |
| triple (0–2) | `f3b7a9…` | 49 † | 91.4% (96/105) | 2.0% |
| after the question fixes (0–2) | `f3b7a9…` | 49 | 97.1% (102/105) | 0.0% |
| **clean triple (3–5)** | `f3b7a9…` | 49 | **91.4% (96/105)** | **12.2%** |

† that triple included q049, later withdrawn, and the pre-rewrite wording of q017
and q026 — so it is the same prompt but not quite the same question set.

**Five triples of a system that did not change, and the variance metric read 0.0,
2.0, 4.3, 10.6 and 12.2 percent.** Two of those are strict replications — same
prompt, same questions, different draws — and each pair lands on opposite sides of
the project's own 10% decision line. The pooled row is not a triple and is not
comparable: the metric counts questions whose outcome *ever* differed, so more runs
read higher by construction rather than because anything got less stable.

A threshold stated as "variance > 10%" therefore measures the sampling budget as
much as the model, and it has been **retired as a trigger** — reported with its
run count, never firing on its own. Reasoning, and what covers the harm it was
actually about:
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