# Plan

Operational only. Reasoning lives in `docs/adr/`.

## Phases

Each phase leaves a working system. Later phases add to it; none is a
prerequisite for something demoable.

### Phase 0 — Data foundation (~32h)

Postgres schema: products, inventory, sales, suppliers, users/roles. Include a
`store_id` column now (multi-store UI is deferred, the column is not). Seeded
generator with seasonality, day-of-week effects, and promotion events.

**Done when:** `make seed` builds a database where a hand-written "top 10 sellers
last month" query returns something that looks like a real store, and re-running
with the same seed produces byte-identical output.

### Phase 1 — Structured Q&A + eval harness (~32h) → FIRST DEMO

Business-context document and schema docs written *before* any SQL prompt.
Read-only DB role, enforced `LIMIT`, few-shot query pairs. Eval set of 30–50
questions with expected result sets.

Frontend scaffold lands here since this is the first UI: Next.js + Tailwind, the
design token plan agreed before any component, typed API client generated from
the OpenAPI schema, SSE consumer.

**Done when:** the harness prints execution accuracy, silent-wrong rate, and
cross-run variance; and a question asked in the web app returns an answer
displayed beside the query that produced it. **Demo beat 1 works.**

**Two things carried in from Phase 0, both of which fall between the phases if
they are not written here:**

1. **Eval expected result sets are computed against `AS_OF_DATE`, never against
   wall-clock.** The seed has a fixed end date so it can be byte-identical on
   re-run, so "last month" means the month before the anchor. An eval written
   against `current_date` rots within 30 days of being written and the README
   number goes stale silently.
2. **The row `LIMIT` is the query wrapper's job.** Phase 0 ships the read-only
   role, forced read-only transactions and a 5s statement timeout. Postgres has
   no max-rows setting, so Phase 1 owes: reject anything that is not a single
   `SELECT`, wrap it as `SELECT * FROM (<sql>) _q LIMIT :n`, and fetch through a
   capped server-side cursor.

### Phase 2 — Corpus ingestion and extraction measurement (~30h)

First hour, two checks. **PII scan:** these are personal documents, so the risk is
home address, phone number, bank details on invoices, signatures, ID numbers — not
commercial sensitivity. One pass before first commit; anything found either gets
the document excluded or the field redacted at source. **Amendments:** check
whether the corpus contains amendments rather than clean supersessions, since that
changes the data model.

Then: Docling parse over real sources, committed. Extraction schema per document
type. Schema-guided extraction, deterministic, raw output committed. Correction
layer with per-fix notes. 30-document hand-labeled gold set and scoring script.
`MANIFEST.csv`, `TIMELINE.md`, `KNOWN_ISSUES.md`, corpus README. Injection
specimens constructed and committed.

**Done when:**
1. `make ingest` run twice produces byte-identical output, asserted in CI.
2. Four-number results block in the top-level README, with denominators.
3. Every gold-set document has committed raw extraction; every correction has a
   note explaining what the pipeline got wrong.
4. `TIMELINE.md` is hand-verified, and a query for a date inside a known gap
   returns "no document in force", distinct from "not found".
5. At least one injection specimen has a committed trace showing the naive
   implementation following it.
6. `KNOWN_ISSUES.md` is non-empty. Flawless handling of 41 real documents means
   the sample was too easy.
7. PII scan complete and recorded in the corpus README.

### Phase 3 — Grounded document Q&A (~20h) → SECOND DEMO

pgvector with local embeddings. Metadata and date pre-filtering. Role-scoped
retrieval applied before generation. Injection defence.

**Done when:** "what were the terms before the renegotiation" returns the correct
historical clause, and a planted injection string in a test supplier PDF provably
fails to change agent behaviour — with the before/after committed as an artifact.
**Demo beat 2 works.**

### Phase 4 — Procurement agent + approval queue (~38h) → THIRD DEMO

Own loop, capped at ~6 tool calls. State as rows: `agent_runs`,
`proposed_actions` with status, payload, expiry, approver. Approval interface in
`web/` — the signature element of the whole project. Reasoning, inputs used,
spending cap, live expiry countdown, stale-input re-validation.

**Done when:** a PO can be drafted, survive a server restart, be approved, and
execute — with full reasoning visible — and an expired or stale proposal correctly
refuses to fire. **Demo beat 3 works.**

### Phase 5 — Polish, ADRs, writeup (~20h)

Demo mode with cached trajectories, replayed through the API so `web/` is
unchanged between live and demo. ADR folder complete. README leading with measured
accuracy numbers.

**Done when:** the three-minute demo runs start to finish with no live API call
able to break it, and the ADRs explain the decisions that matter.

### Phase 6 — Optional, purely additive

Pattern-level anomaly reporting (see ADR-0002 for the pattern-not-people
constraint). Perishable markdown agent. Multi-store UI.

## Hours

Time on this project is irregular and there is no deadline, so weeks are the wrong
unit. **Sessions are.** One session ≈ 3h and ≈ one `PROGRESS.md` update. Adjust
the divisor to your actual sitting.

| Phase | Hours | Sessions | Cumulative |
|---|---|---|---|
| 0 Data foundation | 32 | 11 | 11 |
| 1 Structured Q&A | 32 | 11 | **22 — first demo** |
| 2 Corpus ingestion | 30 | 10 | 32 |
| 3 Document Q&A | 20 | 7 | **39 — second demo** |
| 4 Procurement agent | 38 | 13 | **52 — third demo** |
| 5 Polish | 20 | 7 | 59 — complete |

~172h total; first demo at ~64h.

Phase 0 was budgeted at 20h and came in at ~32h. The overrun is scope that was
accepted, not slippage: temporal supplier terms and prices with exclusion
constraints, a stock-simulating generator rather than independent draws, a
template-database build, generated schema documentation, and pinned-image
determinism. ADR-0007's cost note still quotes the pre-Phase-0 figures, since it
records what was known when that decision was made.

**The only scheduling rule that matters:** each phase leaves a working system, so
stopping after any of them leaves something demoable rather than something broken.
If momentum goes after Phase 1, a measured, documented natural-language interface
over real business data is a complete portfolio piece on its own.

## Cut list

Do not build these.

| Cut | Reason |
|---|---|
| Payment processing | Stub it; adds nothing to any demo beat. |
| Customer-facing product assistant | Free tier can't carry a public surface; generic RAG chatbot. |
| Dynamic pricing | Deferred to Phase 6, not deleted. Flips if the real corpus covers perishables. |
| Multi-store UI | Column now, interface later; multiplies query complexity for an unshowable payoff. |
| Self-correcting retrieval loops | Extra calls per query against a corpus too small to need them. |
| Supplier price comparison as a feature | It's `ORDER BY price, lead_time`. Keep it as a tool, don't showcase it. |
| LLM-as-judge on structured queries | Use deterministic execution-match; save quota. |
| Separate query router | Tool selection does the job. |
| Agent framework (LangGraph et al.) | See ADR-0003. |
| Client state library (Redux, Zustand, React Query) | See ADR-0007. Fetch in server components, `useState` elsewhere. |

## Three-minute demo

Everything above serves this.

**Beat 1 (0:00–0:50)** — "What are we low on that sells fastest?" Grounded answer
with the executed query shown beside it.

**Beat 2 (0:50–1:50)** — "What are our payment terms with Supplier X?" Grounded
answer citing the actual clause and its effective date. Then: *"and what were
they before the renegotiation?"* Correct historical answer.

**Beat 3 (1:50–3:00)** — "Draft a restock order for anything below its reorder
point." Agent produces a draft PO with written reasoning into the approval
queue. Show
the card: reasoning, spending cap, expiry, stale-price warning. Approve one.
Audit entry appears.

Video: 3 minutes, no intro card, no music, cursor visible, and **do not speed up
the agent** — the pause is the point.

## Publishing

Repo + recorded video + local demo mode. No publicly hosted live instance: a
public chat endpoint over the corpus is an open-ended query interface into
personal documents, and free-tier limits mean two simultaneous visitors get an
error.

Three tiers in the README, labelled by what each gets you:

1. **Read-only** — browse `corpus/`, `injection/` traces, ADRs, results. Zero setup.
2. **Run the demo** — `docker compose up`, no API key needed.
3. **Run live** — compose plus your own free-tier key.

A GIF of beat 3 above the fold. Most people never click the video.

## Text-to-SQL: measurement, not argument

Assumes schema docs, business-context document, and a 30–50 question eval set
with expected result sets, each run 3x. **Build the query catalog if any of these
fires:**

| # | Threshold | Why this one |
|---|---|---|
| 1 | Silent-wrong rate > 5% | Tightest, and overrides the rest. Executes cleanly, returns plausible wrong numbers, undetectable live. Measure by comparing result sets, not by whether the query ran. |
| 2 | Execution accuracy < 85% | Catalog maintenance becomes cheaper than generation debugging. |
| 3 | Cross-run variance > 10% | Non-determinism is fatal for a demo run more than once. |
| 4 | Median attempts-to-correct > 1.3 | A retry loop is a quota problem on top of an accuracy problem. |

**Pre-committed regardless of results:** hand-write query templates for the 10–15
questions the demo actually asks. Generated SQL handles the tail. The demo path
is deterministic even if general accuracy is excellent.