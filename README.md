# POS Copilot

A retail POS database with a natural-language query interface, and a procurement
agent that drafts purchase orders into a human approval queue.

<!-- TODO Phase 5: GIF of demo beat 3 — draft PO → approval card → approve → audit entry -->
<!-- TODO Phase 5: link unlisted YouTube video -->

Portfolio project, not a production system. Built solo, free tier only.

## What's actually interesting here

Most RAG portfolio projects show a chatbot answering questions over documents.
Three things here are harder, and each carries its build status, because two of
the three are not standing up yet:

- **Temporal correctness.** Supplier terms change. Ask what the payment terms are
  and you get today's answer; ask what they were before the renegotiation and you
  get the correct historical clause. _Built in the database and the corpus_ — the
  schema carries `valid_period`, and two suppliers have deliberate coverage lapses
  so "nothing in force" is distinguishable from "not found". Extracted terms carry
  `effective_from` / `effective_to` **once extraction runs**, which it has not.
- **A real approval queue.** The agent drafts purchase orders; it does not place
  them. Proposals persist as database rows, survive a server restart, expire, and
  re-validate their inputs before executing — a proposal drafted against a price
  that has since moved refuses to fire. **_Phase 4, not built._**
- **Prompt injection, demonstrated rather than asserted.** The corpus will carry
  labelled injection specimens with committed traces showing a naive
  implementation following them and this one not. **_Phase 2 done-condition 5,
  not built_** — there is no `corpus/injection/` to link to yet.

## Results

Measured, not estimated. Methodology in [`corpus/README.md`](corpus/README.md).

**Extraction** _(n=37 of 40 documents, 2026-08-12, `gemini-3.6-flash` via Vertex,
40 calls, ~$0.18. Gold set derived from the rows the documents were generated
from — see the caveats below, they matter more than the numbers.)_

    Header fields      99.5%   (198/199)
    Line item F1       1.00    (160 rows across 37 documents)
    Hallucination      0.0%    (0/160 rows)
    Miss               0.0%    (0/160 rows)

**Read the denominators before the percentages.**

- **37 of 40, not 40 of 40.** Three policies are free-standing — no database row
  was behind them, so there is nothing to score and inventing a denominator would
  be worse than a smaller one.
- **Two clause-level amendments are excluded from header scoring**, and that
  exclusion is the most interesting result here. They restate three clauses and
  nothing else; the `supplier_terms` row carries the full inherited set, so every
  clause the document deliberately omits reads as a miss. A wide superseding table
  **structurally cannot score a clause-level amendment** — which is precisely the
  case the clause-level provenance decision was made for, demonstrated rather than
  argued. See [`corpus/corrections/`](corpus/corrections/).
- **The one header miss is OCR**, not reasoning: a scanned, skewed contract whose
  letterhead did not survive rasterisation. Every number in the same document is
  exact.
- **"0% hallucination" is a claim about rows, and it was nearly a false one.**
  `supplier_code` used to be scored on catalogs — where no catalog prints one.
  Two extractions inferred `SUP-01` from the supplier name and scored *correct*;
  the one that honestly returned null scored as a *miss*. The metric was rewarding
  the hallucination and penalising the refusal. Fixed, and written up rather than
  quietly dropped.
- **The gold set cannot tell a model failure from a document failure.** Where the
  generator wrote `&amp;` into a PDF, faithful extraction scores as an error. Both
  cases are in [`corpus/corrections/`](corpus/corrections/), and two of the four
  notes there say the pipeline was right and the corpus was wrong.

Scored by `make eval-extraction` — deterministic comparison against Postgres, no
LLM-as-judge, free to re-run.

> ### ⚠️ The text-to-SQL block below is STALE and has not been re-measured
>
> Every figure was scored against seed fingerprint `206fb7a8e55164f9`. **The seed
> is now `e1ca4fb60f9e710e`** — two suppliers were given deliberate coverage
> lapses on 2026-08-11 so that "no document in force" could be told apart from
> "not found" — and **two expected result sets changed with it**: q017 and q048,
> both of which read `supplier_terms` by period.
>
> The error is probably small and bounded, two questions with one changed value
> each. But "probably" is not a measurement, and these are published as if they
> were one. **Re-scoring is not free:** `evals/.cache/` is gitignored and exists
> only on the machine that produced it, so restoring these numbers means
> re-running — 147 calls, ~$3.30, and a Vertex service account.
> `docs/CONVENTIONS.md` allows exactly two responses to a number whose inputs
> moved: re-run it, or mark it stale. This is the mark.

**Text-to-SQL** _(n=49 questions × 3 runs = 147 responses, 2026-08-09, prompt
`f3b7a9193a56f10d`, `gemini-3.6-flash` via Vertex, ~$3.32, **seed
`206fb7a8e55164f9` — superseded**)_

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

**1. Read only — no setup.** Browse [`corpus/sources/`](corpus/sources/) for the
40 source documents, [`corpus/parsed/`](corpus/parsed/) for what Docling made of
them, and [`docs/adr/`](docs/adr/) for why things are the way they are.
Extractions and injection traces are Phase 2 and are not here yet.

**2. Run the demo — no API key.**

    cp .env.example .env
    docker compose up

Opens on `localhost:3000` in demo mode: real UI, real data, replayed agent runs.
Cached trajectories load through the same code path that would call a model.

**3. Run live — your own free-tier key.** Add a key to `.env`, set
`DEMO_MODE=false`, and `docker compose up`. Optionally
`docker compose --profile local-models up` to run generation locally via Ollama.

No hosted instance. Free-tier limits mean two simultaneous visitors get an error,
and an open-ended public chat endpoint over any corpus is a standing invitation to
use someone else's quota. The corpus being synthetic removes the confidentiality
reason for this, not the other two.

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

**Synthetic, and generated from the seeded database** — supplier contracts
correspond to `supplier_terms` periods, invoices to `purchase_orders`, catalogs to
`supplier_prices`, so a document and the row it describes cannot disagree. That is
what makes the temporal demo honest: "what were the terms before the
renegotiation" is answerable from the documents *and* checkable against the data.

**It is not a corpus of real documents, and the extraction numbers should be read
with that in front of them.** The difficulty in it is difficulty that was chosen —
scanned pages, skewed tables, a supplier template that puts totals above line
items — so the measurement says the pipeline handles the failures we thought of,
which is a weaker claim than surviving documents nobody designed. Composition, the
injected difficulty, and known extraction failures are in
[`corpus/README.md`](corpus/README.md) — [`KNOWN_ISSUES.md`](corpus/KNOWN_ISSUES.md)
is deliberately non-empty.

Raw pipeline output in `corpus/extracted/` is never hand-edited; hand fixes live
in `corpus/corrections/` with a note per fix saying what the pipeline got wrong.
That separation is what will make the accuracy number above believable —
**neither directory exists yet**, because extraction has never been run.

## Reproducibility

- **Parse layer:** byte-identical **within a pinned environment**, asserted in CI
  on a committed 4-document sample. **Not across environments, and that was
  measured rather than assumed:** re-parsing the corpus on a second platform put
  **5 of 40 documents** in the divergent set — four heading-versus-paragraph flips
  and one lost table. The sample deliberately includes the document that diverges,
  so `make verify-parse` is an environment gate rather than a formality. See
  [`corpus/KNOWN_ISSUES.md`](corpus/KNOWN_ISSUES.md) entry 2.
- **Artifact integrity:** SHA-256 verified against `corpus/CHECKSUMS.txt` on every
  push — 82 artifacts, with nothing unlisted permitted to be present.
- **Extraction layer:** pinned model string **and serving location**, both
  recorded in `corpus/PIPELINE.json`. **No sampling parameters are sent:**
  `temperature`, `top_p` and `top_k` are deprecated and ignored on these models,
  so a `temperature=0` in the code would look like a reproducibility control while
  doing nothing. Reproducibility here is therefore **measured, not asserted from a
  parameter** — and it has not been measured, because extraction has never run.

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

**Phase 1 closed 2026-08-09 — structured Q&A.** A question asked in the web app
returns an answer beside the SQL that produced it, with no key and no quota; the
live generation path sits beside the canned one, opt-in, and has been proven
against the real model. The eval harness reports execution accuracy, silent-wrong
rate and cross-run variance, measured six times. The numbers are in *Results*
above, and what they do and don't support is in
[`docs/PROGRESS.md`](docs/PROGRESS.md). It was closed with known instrument debt,
listed there rather than hidden.

**Phase 2 in progress — corpus ingestion.** The corpus exists: 40 synthetic
documents generated from the seeded database, byte-identical on regeneration,
and parsed with Docling into [`corpus/parsed/`](corpus/parsed/). A 4-document
sample is re-parsed and byte-compared in CI on every push. **Extraction is built
and has never been run** — prompt, schemas, validator and runner are all exercised
against a stub, and no model call has ever been made — so every extraction number
above is still blank and `corpus/extracted/` does not exist. Four of the phase's
seven done-conditions hold. See [`docs/PLAN.md`](docs/PLAN.md).