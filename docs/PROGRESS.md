# Progress

**Read this first. Write it last.** This is the only memory across sessions.

Keep it short. Delete resolved items rather than accumulating history — git has
the history. This file answers one question: what does the next session need?

---

## Current phase

**Phase 0 — Data foundation. Complete.** Next up is Phase 1, structured Q&A.

Definition of done is in `docs/PLAN.md`.

## Where things stand

| Phase | Status | Note |
|---|---|---|
| 0 Data foundation | **done** | ~32h against a 20h budget; PLAN.md updated |
| 1 Structured Q&A | not started | |
| 2 Corpus ingestion | not started | |
| 3 Document Q&A | not started | |
| 4 Procurement agent | not started | |
| 5 Polish | not started | |

## Last session

_Date:_ 2026-08-06
_What landed:_ Phase 0 complete and pushed. Then the locale was resolved to
**India** and the whole dataset regenerated: INR, Asia/Kolkata, a Maharashtra
chain (Pune / Nashik / Nagpur), an Indian grocery catalogue, GST by category
slab, and a real festival model. ADR-0004's reset budget amended to the
measured numbers; CONVENTIONS gained the migration→`make schema-doc` rule.
_What didn't, and why:_ Phase 1 has not started. The locale change had to land
first and finish clean.
_Anything half-finished someone would trip over:_ No.
_Is the system in a working state?_ Yes. `make db` → `make test` green: 32 tests,
`ruff` clean, seed byte-identical at both sizes, `schema.md` current.

## Next session should

1. **The LIMIT wrapper** — the named debt below. Reject anything that is not a
   single `SELECT`, wrap as `SELECT * FROM (<sql>) _q LIMIT :n`, fetch through
   a capped server-side cursor.
2. **SQL generation** against `sql_generate.md`, then the first eval run:
   `make eval-sql`, 41 questions × 3 runs. Report execution accuracy three
   ways — overall, view-covered, not-view-covered — and read the ADR-0001
   thresholds off the **not-view-covered** number.
3. **Next.js scaffold and the query UI.** Design tokens get proposed and agreed
   before any component is written (CONVENTIONS → Frontend).

## Phase 1 so far

- `api/prompts/context/business_context.md` — written first, before any prompt
  work or eval question, per ADR-0001. Every factual claim in it was checked
  against the built database rather than the draft.
- `evals/sql/questions.jsonl` — 41 questions, expected result sets **generated**
  by executing hand-written reference SQL (`make eval-expectations`), never
  typed. Pinned to the seed by `seed_fingerprint`; a pytest fails when they
  drift apart. `evals/sql/README.md` documents the schema and the trap coverage.
- Four expectation kinds: `rows` (35), `empty` (1), `refusal` (3),
  `disambiguation` (2). `empty` is a distinct kind on purpose — an empty
  expectation filed under `rows` scores every wrong query as correct, and
  `eval_expectations.py` treats that as a broken question rather than a result.
- **11 view-covered, 30 not.** The ADR-0001 threshold is judged on the 30.

## Model providers and live limits

Decided 2026-08-06. Reasoning in **ADR-0009** — the split is on **data terms**,
not rate limits.

| Role | Provider | Tier | Model |
|---|---|---|---|
| `PLAN` | Gemini API | Free | Flash, pinned version string |
| `CLASSIFY` | Gemini API, or local Ollama if RAM allows | Free | Flash-Lite |
| `EXTRACT` | Vertex AI, service account | **Paid** | Phase 2 only |

**Mistral: fallback, documented, deliberately not wired.**

### Terms — verified 2026-08-06, re-check before Phase 2

- **Free tier trains on your data.** [ai.google.dev/gemini-api/terms](https://ai.google.dev/gemini-api/terms)
  (effective 2026-03-23, updated 2026-04-28): Google "uses the content you
  submit ... to provide, improve, and develop Google products and services",
  and "human reviewers may read, annotate, and process your API input and
  output." The page says outright: do not submit personal information to the
  unpaid services.
- **Paid tier does not.** Same page: Google "doesn't use your prompts ... or
  responses to improve our products".
- **Vertex** states customer data stays out of the foundation model training
  corpus — but ⚠️ **this was confirmed from Google Cloud documentation, not the
  canonical Service Specific Terms, which would not load.** Read those directly
  before the first extraction run over real documents. If they disagree,
  ADR-0009 is void.

### Rate limits — NOT YET VERIFIED, and only you can

Google's rate-limit page no longer publishes a table. It says limits "can be
viewed in Google AI Studio" and links
`https://aistudio.google.com/rate-limit?timeRange=last-28-days`. That view is
behind your login, so **these numbers have to come from you**, per project
behind the key.

Fill in before the first eval run — they set iteration speed and nothing else
should be guessed from blogs:

| Model | RPM | TPM | RPD |
|---|---|---|---|
| `gemini-3.6-flash` (PLAN) | __ | __ | __ |
| `gemini-3.5-flash-lite` (CLASSIFY) | __ | __ | __ |

⚠️ **Also confirm `gemini-3.6-flash` is free-tier eligible in YOUR project.**
It is two weeks old (GA 2026-07-21) and appearing on the public pricing page is
not the same as being enabled for a given project. If it is not, fall back to
`gemini-3.5-flash` and record the change.

Third-party figures circulating for the free tier — 10 RPM / 250 RPD for Flash,
15 RPM / 1000 RPD for Flash-Lite, 250k TPM — are **unverified blog numbers and
should not be relied on.** One of the same sources claimed Pro was removed from
the free tier in April 2026, which Google's own pricing page (updated
2026-08-05) contradicts: `gemini-2.5-pro` is listed as free-tier eligible. That
is the accuracy level of those tables.

**Free-tier eligible Flash models**, from the official pricing page
(2026-08-05): `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`,
`gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`. Pin one
exactly; never a floating alias.

**Budget:** a GCP budget alert must exist before the first Vertex call.

### Sampling parameters are gone

`temperature`, `top_p` and `top_k` are **deprecated and ignored** on both chosen
models, and return HTTP 400 on future generations (Gemini release notes,
2026-07-21). ADR-0006 is amended: extraction reproducibility is now **measured
empirically**, not asserted from a sampling parameter, and nothing in this
project should send those fields. Consequence for ADR-0001 threshold 3: it now
measures the model's inherent nondeterminism rather than prompt instability —
still the right thing to measure, but do not read it as a prompt-quality
metric.

## Locale — resolved, India

Currency INR, timezone Asia/Kolkata, modelled as a Maharashtra grocery chain
(Kothrud/Pune, Gangapur Road/Nashik, Dharampeth/Nagpur). This is now final and
the eval set can be written against it.

**Two things still to check against the corpus when it lands**, both flagged in
the LOCALE block of `api/scripts/seed.py`:

- **Festival dates.** Solar ones are fixed; the lunisolar and lunar ones —
  Diwali, Holi, Ganesh Chaturthi, and especially the two Eids — are marked
  `APPROX` in the code. Wrong festival dates are visible to any Indian reviewer.
- **GST slabs.** India simplified the slab structure during 2025, so the
  per-category rates are indicative. Real invoices in the corpus carry the real
  rates and those win.

Correcting either means editing that block, `make seed-generate` at both sizes,
and committing the regenerated `seed/small/` + `seed/CHECKSUMS.txt` — **which
invalidates every eval expected result set written before it.** Do it before
Phase 1's eval set if it is going to happen at all.

## Named debt carried into Phase 1

- **The `LIMIT` wrapper.** Postgres has no max-rows setting, so the read-only
  role cannot enforce a row cap — CLAUDE.md rule 4 has been amended to say so.
  Phase 0 ships `pos_readonly` with `default_transaction_read_only`, a 5s
  `statement_timeout`, and no grant on `users` or `sale_operators`. Phase 1
  owes: reject anything that is not a single `SELECT`, wrap as
  `SELECT * FROM (<sql>) _q LIMIT :n`, fetch through a capped server-side
  cursor. Also recorded in `docs/PLAN.md` under Phase 1.
- **`view_covered` on every eval question.** Already written into ADR-0001.
  `v_stock_status` and friends make some questions near-trivial; the threshold-2
  decision is evaluated against the not-view-covered number, or the measurement
  flatters itself.
- **`AS_OF_DATE`, not wall-clock.** `DATA_END_DATE = 2026-06-30` is a constant
  in `seed.py` and is what makes byte-identity possible. `sql_generate.md` now
  has the `{as_of_date}` placeholder and forbids `current_date`;
  `business_context.md` must teach the same thing when it is written.
- **`api/prompts/context/business_context.md` does not exist yet**, and the
  top-level README already links to it. Dead link until Phase 1 writes it.

## Facts about the data someone will otherwise rediscover the hard way

- **`small` and `full` are independent datasets, not subset and superset.**
  Reference data (600 products, 18 categories, 12 suppliers) is identical;
  stores, history length and volume differ. **Every eval runs against `full`.**
  An eval written against `small` will not hold.
- **`make db` is the slow path (~60s at full); `make reset` is the fast one
  (~2–6s).** `make db` builds `pos_template` and marks it a template; `reset`
  clones it, which is a file copy. This is also the ADR-0005 test-isolation
  mechanism, and it answers ADR-0004's worry about `agent_runs` churn in Phase 4
  forcing a full rebuild each time.
- **Seed generation runs in a digest-pinned `python:3.12-slim`**, in both the
  Make target and CI. Bare Python is not enough: libm differences can flip a
  Poisson draw and the tzdata version moves timestamps. The claim is
  byte-identical *in the pinned image*, asserted in CI at both sizes.
- **`sale_lines.quantity` is signed** — negative on returns — so `SUM(quantity)`
  is net, not gross. `daily_product_sales` names `units_sold`, `return_units`
  and `net_units` separately. Good eval question; likely silent-wrong trap.
- **The festive season is the strongest signal in the data.** Navratri →
  Dussehra → Dhanteras → Diwali is one continuous six-week build, not four
  spikes: ₹417k/day against a ₹267k/day baseline, peaking at 2.75x on 17 Oct
  2025 (the day before Dhanteras) and collapsing to a 12-day slump afterwards.
  Festivals are their own factor (`Festival` + `build_day_factors`), separate
  from the category sinusoid, because a sinusoid is symmetric and slow and this
  shape is neither. Overlapping festivals combine by **max, not product** —
  multiplying four ramps produces a number no shop has seen.
- **`full` contains exactly one Diwali (Oct 2025); `small` contains none**, since
  `small` starts 2026-01-02 and Diwali 2026 is past `DATA_END_DATE`. Do not
  write a Diwali eval question and test it on `small`.
- **Ganesh Chaturthi and Gudi Padwa are weighted per store** — Pune indexes
  above Nagpur. Everything else applies chain-wide.
- **GST is per category AND per date.** The 22 September 2025 reform is inside
  the window: slabs went 0/5/12/18/28 → 0/5/18/40, aerated drinks 28→40,
  dairy/snacks/ready-to-cook/personal care/health/baby/pooja 12→5. Rates live
  in `gst_rates` with the same `valid_period @> date` pattern as
  `supplier_terms`. Effective rate measured at 8.42% before and 6.68% after;
  the naive blend across the boundary is 7.52%, **true of no period**.
  `sales.subtotal` is net of tax and `total = subtotal + tax_total`; "revenue"
  normally means `subtotal`.
- **Regional festival weighting exists but is NOT measurable at store level.**
  Ganesh Chaturthi and Gudi Padwa are weighted per store (Pune 1.00, Nashik
  0.88, Nagpur 0.72), but the `max` combination with unweighted national
  festivals in the same window dilutes it below Poisson noise. An eval question
  about it had an expected answer that contradicted its own premise, and was
  replaced (q027 is now about store size confounding a comparison, which the
  data does support). **Do not write an eval question about regional festival
  differences** without first widening the spread and re-measuring.
- **Prices are category-banded, not free log-normal** (`CATEGORY_PRICE_MEDIAN`
  × `variant_price_factor`). Without that the generator produced ₹225 bananas
  beside a ₹78 five-litre oil jar — which loads cleanly, passes every
  constraint, and makes any revenue question answer noise.
- **Velocity divides by days the product was *available*,** not by 30.
  `stockout_days` exists because sales are capped by stock, so the products a
  restock question is about are exactly the ones whose sales understate demand.
- **`seed/full/` is gitignored** (63MB). `seed/small/` is committed (5.5MB), and
  `seed/CHECKSUMS.txt` covers both, so the byte-identity claim is verifiable for
  `full` without shipping it.
- 21 of 600 products end at zero stock and ~150 sit below reorder point. That is
  realistic, not a defect — but it means the beat-1 query wants
  `AND on_hand > 0` to ask "about to run out" rather than "already out", and a
  `units_per_day DESC` tiebreak so the ordering is total.

## Open questions — ask me, don't decide

These are unresolved by design. If you hit one, stop.

- **Corpus size.** Estimated ~40 documents, never confirmed. If the whole corpus
  is under 40, label all of it and skip gold-set sampling.
- **Amendments vs. supersessions.** Phase 2, hour one. Phase 0's `supplier_terms`
  is a wide table that supersedes as a set, which is right for supersessions and
  right for text-to-SQL. If real amendments exist, the answer is a narrow
  `supplier_term_clauses` table for clause-level provenance with `supplier_terms`
  kept as the queryable projection — not a reshape. Still needs deciding.
- **Available RAM.** Determines the local model tier: 16GB+ runs an 8B at Q4_K_M
  for `CLASSIFY` and `EXTRACT`; 8–12GB runs a 3–4B and sends `PLAN` to API; under
  8GB means no local generation. Embeddings stay local at every tier.
- **Which free-tier provider** for `PLAN`. Not chosen. Check current limits before
  committing — they change monthly.
- **Text-to-SQL outcome.** Deliberately open. Settled by Phase 1 measurement
  against the four thresholds in `PLAN.md`.
- **Design tokens.** Palette, type pairing, and the approval-card wireframe are not
  chosen. Propose before building any component (`CONVENTIONS.md` → Frontend).
- **Whether the corpus covers perishables.** If yes, the dynamic pricing cut flips
  and it belongs in Phase 6.
- **Role-scoping policy.** Decided as own-store only, two DB roles, no
  column-level cost/margin restriction. Cost-hiding stays additive. The
  `sql_generate.md § Access scope` TODO is Phase 1's to fill in.

**Resolved — don't re-ask:** hours (session-based, see `PLAN.md`), document
clearance (personal, publishable; PII scan still required in Phase 2), frontend
(Next.js + Tailwind, ADR-0007).

## Measured numbers

Fill in as they land. These go in the top-level README.

_Extraction (n=__ hand-labeled documents):_ header fields __%, line item F1 __,
hallucination __%, miss __%

_SQL (n=__ questions, 3 runs each):_ execution accuracy __%, silent-wrong __%,
cross-run variance __%, median attempts-to-correct __
_(report overall, view-covered, and not-view-covered — see ADR-0001)_

_Injection specimens:_ __ of __ held

## Decisions made mid-build

Anything decided in a session that isn't yet an ADR. Promote or delete.

- **`effective_from`/`effective_to` landed in 001, not Phase 2.** Adding them
  later would have meant a backfill plus rewriting every Phase 1 query that read
  `suppliers.payment_terms_days`. A generated `valid_period daterange` column
  carries half-open `[from, to)` semantics natively, so a query says
  `valid_period @> DATE '...'` and cannot get the boundary wrong. A gist
  exclusion constraint forbids overlap and permits gaps — gaps are how "no terms
  in force" stays distinguishable from "supplier not found". Verified against
  PG16 before the migration was written.
- **`sale_operators` is a separate table with no grant to `pos_readonly`.** ADR-0002
  says the agent reports patterns, never people; this makes the query interface
  structurally incapable of returning who rang up a sale, rather than trusting a
  prompt. Staff display names are `Clerk 03`-style labels, never person-like.
  Candidate for promoting into ADR-0002 as an implementation note.
- **`schema.md` is generated from `COMMENT ON` statements** by `make schema-doc`,
  and CI fails if the committed copy is stale. `business_context.md` stays
  hand-written. Candidate for an ADR if it survives Phase 1.
- **`store_id` and `business_date` are denormalised onto `sale_lines`** and held
  true by a three-column composite foreign key, so velocity queries never join
  the header and the copies cannot drift.
