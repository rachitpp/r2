# Progress

**Read this first. Write it last.** This is the only memory across sessions.

Keep it short. Delete resolved items rather than accumulating history — git has
the history. This file answers one question: what does the next session need?

---

## Current phase

**Phase 1 — Structured Q&A. In progress, at the diagnosis stage.** The 47×1 run
is measured and every failure is now diagnosed; instrument fixes are unblocked
but deliberately not yet applied. See `evals/DIAGNOSIS-2026-08-07.md`.

Definition of done is in `docs/PLAN.md`.

## Where things stand

| Phase | Status | Note |
|---|---|---|
| 0 Data foundation | **done** | ~32h against a 20h budget; PLAN.md updated |
| 1 Structured Q&A | **in progress** | LIMIT wrapper done; eval runner built; 47×1 measured; failure diagnosis complete; fixes pending, then runs 1–2; UI not started |
| 2 Corpus ingestion | not started | |
| 3 Document Q&A | not started | |
| 4 Procurement agent | not started | |
| 5 Polish | not started | |

## Last session

_Date:_ 2026-08-07
_What landed:_ Failure diagnosis completed and **the previous diagnosis audited**
— model SQL and reference executed and compared field by field, **zero model
calls**, every response already cached. All 14 failures now bucketed: 11
instrument, 2 model, 1 context.

Four findings that were not just new diagnoses:

- **The seventh axis was mis-stated and its evidence wrong in 3 of 4 questions.**
  q019 was recorded as "numbers identical, label text only, verified by hand" —
  it is **8.30 vs 8.23 and 7.08 vs 6.73**. The real axis is **row identity**
  (`ST-01` vs `Kothrud`), and q019 belongs with q045 instead.
- **q004 re-bucketed `ambiguous` → `context`**, against the favourable
  direction. `ambiguous` should mean no context document could settle it; this
  one settles in a sentence.
- **The rotation process half-fixed a known defect.** Rotation 5 edited q045's
  cover threshold with the definition open and left `below_reorder_point` — a
  predicate belonging to a *different* published phrase — in place.
- **q043 is a bucket flip, not a fresh finding**, and it moves model failures
  1 → 2.

Then the diagnosis record itself was audited, and **the q019 entry recorded a
hand-verification that never ran**: it reported 8.23 / 6.73 as the model's
output, which are the constants `business_context.md` publishes as the true
rates. The expected values were written into the observed slot. Every numeric
claim in the file was re-executed as a result — **q018 (8.23, split verified),
q009's 54,759 / 54,594, q001's unsound pass all hold**; q026's timing does not
reproduce (5.33s, not 1.59s) but its verdict strengthens. As a wholesale
control, **46 of 47 cached responses reproduce their recorded outcome** — the
run record is sound; the defect was in the prose.

The q045 half-fix hypothesis was **checked and withdrawn** — git archaeology
over every reference edit found it to be one occurrence, not a class. What it
found instead: **8 of 14 failing references were never revised at all.** The
rotation gap is reach, not depth. Agreement is not verification.

_What didn't, and why:_ No fixes applied. The disambiguation ruling is
**recorded and restated on the corrected axis** — identity is not signal, so a
reading is read off the predicate — and deliberately not implemented.
**A pending decision is recorded for next sitting: declare instrument v2 and
drop the fix cap**, on the ground that q004's context fix voids the fingerprint
regardless, so the cap now protects no comparison.
_Anything half-finished someone would trip over:_ The 21 unaudited passes. 1 of
the 9 sampled was unsound, so expect ~2 more to be hiding something. Also
unchecked: whether any **other** reference borrows a predicate from a
neighbouring definition, as q045 did.
_Is the system in a working state?_ Yes. Nothing executable changed — only
`evals/DIAGNOSIS-2026-08-07.md` and this file. 158 passed, 25 skipped.
Credential history verified clean; `make hooks` now active.

## Corrections that must reach any pasted handoff

**There is no handoff document in this repo.** The state doc pasted into new
sessions is maintained outside it, so these corrections cannot be applied here —
apply them by hand, or the next session starts from falsified premises. This
project has already lost one session to a stale state doc.

1. **The seven-axis table is wrong.** It publishes "free-text labels the query
   invents" with a `'Before Sep 22, 2025'` example. The real axis is **row
   identity** — which column names a row (`stores.code` vs `stores.name`) — and
   the example is worse than wrong: **q019 did not return the reference's
   numbers.** It returned 8.30 / 7.08 against 8.23 / 6.73. There are also two
   further axes: **ratio magnitude** (fraction vs percent) and
   **disambiguation was unscoreable** against a criterion the prompt forbids.
2. **q043 is not a reference-author error.** Its `reference_sql` was never
   edited. Rotation 4 fixed its *question*, which had not named the period the
   reference already filtered on. It is now diagnosed **`model`** — it used
   `subtotal` where the context says to use `total` for what a customer paid.
3. **The stopping rule is falsified.** "Every question model-tested and the
   instrument corrected against it" was satisfied, and 8 of 14 failing
   references were never revised. Replaced by the **predicate-to-words trace** —
   see `evals/README.md` → *When to stop rotating*. Agreement is a null result.
4. **q004 is `context`, not `ambiguous`** — so its fix edits
   `business_context.md` and voids the prompt fingerprint and all 47 cached
   responses.
5. **A pending decision is recorded**: declare instrument v2 and replace the fix
   cap with an enumerate-then-fix gate. See the end of
   `evals/DIAGNOSIS-2026-08-07.md`.

`docs/prompts/phase-1-structured-qa.md` exists and is **0 bytes**. If the
handoff should live in the repo, that is where it belongs — not decided.

## Next session should

1. ~~Audit the 21 unaudited passes.~~ **Done — all 30 passes now read.** 19 of
   21 sound; **q005** carries a stale `intent` (says `on_hand <= 5`; question
   and reference say `<= 2`) and **q008**'s reference carries an unstated
   `HAVING sum(units_sold) > 200`. Note `is_active = true` is a structural
   no-op — all 600 products are active — so the many generated queries adding
   it are unstated predicates the eval cannot detect.
2. **Apply the reference fixes** — the numbered list at the end of
   `evals/DIAGNOSIS-2026-08-07.md`. Eight reference-level defects, at the 10-fix
   cap. Item 9 (disambiguation) is already ruled and needs implementing in
   `scoring.py`, not deciding.
3. **Keep the q004 context edit separate and last.** It is the one fix that
   touches `business_context.md`, which **voids the prompt fingerprint and all
   47 cached responses** — another $0.99. Reference fixes re-score for free;
   bundling the context edit with them throws that away.
4. **Then re-score, then buy runs 1 and 2.**
5. **Next.js scaffold and the query UI.** Design tokens get proposed and agreed
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

## KEY ROTATION PENDING — do not use the current credential

The service account JSON arrived in the repo working tree, untracked and
un-ignored, while every commit used `git add -A`. Not committed and not in
history — verified — but its disposition is not fully accountable, so it is
being **rotated**: new key in the console, old one deleted, replacement never
placed inside the repo directory.

Two layers now guard this, because ignore patterns only catch anticipated
filenames:

1. `.gitignore` carries broad credential patterns, not just the one filename.
2. `.githooks/pre-commit` greps STAGED CONTENT for the markers a service
   account JSON and a PEM private key always carry, plus the AI Studio key
   shape. The patterns live in the hook; they are deliberately not reproduced
   here, because a document quoting them literally trips the hook — which is
   how this paragraph got written. Enable with `make hooks`. Verified to block
   the real key and to pass a normal commit.

## Vertex: verified working, one surprise

- Token mints from the service account; `gemini-3.6-flash` answers.
- **It serves from `location=global` ONLY** — 404 in us-central1 and
  asia-south1. Model string and serving location are independent variables and
  only the string was being pinned. `corpus/PIPELINE.json` now records both,
  and ADR-0006's claim is amended to "pinned model string AND serving
  location".
- For Phase 2, `location=global` needs a data-residency decision before real
  documents are sent.

**Still unverified: who pays.** The Cloud Billing API is not enabled on the
project, so credit coverage, balance and expiry cannot be read from here.
Calls succeed, which proves access and quota — not that credit is being drawn
rather than a card.

## BLOCKED: no GCP credential exists in this environment

ADR-0010 routes every model call through Vertex. **It cannot be executed yet.**
There is no `gcloud`, no service account, no `GOOGLE_APPLICATION_CREDENTIALS`,
and nothing GCP-shaped in `.env` beyond the AI Studio key. The service account
ADR-0009 assumed for Phase 2 does not exist.

Three things need checking in the console before any Vertex call, none of which
could be done from here:

1. **Do credits actually cover Gemini on Vertex?** The billing page is explicit
   that they do NOT cover AI Studio, and **silent** about Vertex. The only
   Vertex exclusion found names *partner* models (Claude, Llama, Mistral in
   Model Garden), not first-party Gemini — so probably covered, but "probably"
   bills a card when wrong.
2. **Remaining credit and expiry.** 90 days from signup, not first use. If the
   account is not new the balance may already be zero.
3. **`gemini-3.6-flash` on Vertex, in region, exact model string.** A mismatched
   pin breaks reproducibility silently, and after ADR-0006 the pinned string is
   the entire reproducibility claim.

Also: Vertex is now **Gemini Enterprise Agent Platform** (renamed May 2026);
console and doc paths have moved.

## RPD MEASURED: 20 per day. This changes the plan.

Not from a blog and not from AI Studio — from the `429` body itself, which
names the quota:

    metric  generativelanguage.googleapis.com/generate_content_free_tier_requests
    id      GenerateRequestsPerDayPerProjectPerModel-FreeTier
    value   20
    model   gemini-3.6-flash

**Twenty requests per day**, scoped per project PER MODEL. The arithmetic:

| | calls | at 20/day |
|---|---|---|
| rotation 5x1 | 5 | 0.2 days |
| 46 x 1 | 46 | 2.3 days |
| 46 x 3 | 138 | 6.9 days |
| **total** | **189** | **9.4 days** |

The prompt is ~11,600 tokens (schema.md and business_context.md dominate), so
the whole measurement is 2.19M input tokens. At the paid Flash rate of $1.50/M
in and $7.50/M out that is **about $3.70 for the entire thing**.

So the choice is roughly: **$3.70, or nine days.** Needs a ruling — see the
options in the session report. Note the quota is per MODEL, so a different free
model carries its own 20/day, but measuring across two models measures two
models.

## Free-tier daily quota EXHAUSTED 2026-08-07

A re-score hit `429` and six backoff attempts spanning roughly two minutes did
not clear it, which points at the **daily** cap rather than requests-per-minute.
No more model calls today; it resets at midnight Pacific.

The cache did not save this run, and correctly so: `business_context.md`
changed, so the prompt fingerprint changed, so every cached answer describes a
prompt that no longer exists. Caching protects a *re-run of the same prompt*,
not a re-run after editing one.

**Still needed: the real RPM/TPM/RPD from `aistudio.google.com/rate-limit`.**
Roughly 20 calls were spent today across three staged runs.

## Eval instrument — three defects found, all fixed

Stage 1 (5 questions x 1 run, `gemini-3.6-flash`) returned 0/4. **That is not a
measurement of the model. It is the instrument failing**, and no result file was
kept, because a 0% sitting in `evals/results/` would be a lie.

Two defects, both mine:

1. **17 of 38 scorable questions have their row count fixed by an arbitrary
   `LIMIT` the question never asks for.** "What should we reorder at Nashik?"
   has no natural answer length; the reference says `LIMIT 20` and the model
   said `LIMIT 100`. Verified on q004: **the model's first 20 rows match the
   reference's 20 exactly.** It was right and scored wrong. Same shape on q005,
   q002.
2. **q001's reference filters `store_id = 1` although the question names no
   store** — which contradicts `sql_generate.md`'s own rule ("when it does not
   name a store, aggregate across stores"). The model followed the rule; the
   reference broke it. 139 rows vs the correct 440.

Ordering has the same problem: 19 reference queries impose an `ORDER BY` the
question does not imply.

All three were one family: **the reference encoded a choice the question did
not determine.** Enumerated on paper and closed together rather than one at a
time — see `evals/README.md` for the full table.

- `result_shape` (4 kinds) fixes row count and row order.
- Sub-multiset row matching plus `answer_columns` fixes column selection,
  column order and column names. The expectation now holds ONLY what the
  question asks for; the reference still SELECTs context for a human reader.
- `tolerance.py` fixes rounding and rendering: absolute tolerances only,
  compared at the coarser of the two precisions.

Third staged run (fresh questions) went 3/5, with both failures again the
instrument — q029 read as singular and the model answered with one row
correctly; q040's reference demanded a PO count the question never asked for.
Both fixed. **The next staged run is the first that can be believed.**

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
| `gemini-3.6-flash` (PLAN) | __ | __ | __ |   <- CONFIRMED enabled and answering
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

- ~~**The `LIMIT` wrapper.**~~ **Discharged.** `api/src/pos_copilot/readonly_sql.py`
  ships all four layers — single-`SELECT` check over a scanner that understands
  literals, dollar-quoting and comments; write/DDL rejection including inside a
  CTE; the bounding subquery at `max_rows + 1` so truncation is a fact rather
  than an inference; and a named server-side cursor with a capped itersize.
  Plus the scope tripwire, which refuses rather than filters (rule 5).
- **`view_covered` on every eval question.** Already written into ADR-0001.
  `v_stock_status` and friends make some questions near-trivial; the threshold-2
  decision is evaluated against the not-view-covered number, or the measurement
  flatters itself.
- **`AS_OF_DATE`, not wall-clock.** `DATA_END_DATE = 2026-06-30` is a constant
  in `seed.py` and is what makes byte-identity possible. `sql_generate.md` now
  has the `{as_of_date}` placeholder and forbids `current_date`;
  `business_context.md` must teach the same thing when it is written.
- ~~**`business_context.md` does not exist yet.**~~ **Discharged.** Written, and
  it now carries the working definitions ("fast-moving", "about to run out",
  "a top seller") with the number behind each. Note that q045 caught a reference
  contradicting one of those published definitions — the document is now
  authoritative enough that references have to be checked against it.

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
