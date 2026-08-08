# Progress

**Read this first. Write it last.** This is the only memory across sessions.

Keep it short. Delete resolved items rather than accumulating history — git has
the history. This file answers one question: what does the next session need?

---

## Current phase

**Phase 1 — Structured Q&A. Both halves of the definition of done are met.**

`docs/PLAN.md` says Phase 1 is done when the harness prints execution accuracy,
silent-wrong and cross-run variance **and** a question asked in the web app
returns an answer beside the query that produced it.

- **Harness: done, and now measured four times** — 49 questions × 3 runs on the
  current prompt, plus six runs of the previous one. The four samples disagree
  with each other in ways that matter; see *Last session*.
- **Web app: the query view exists and works.** `web/` is a Next.js App Router
  app with the proposed palette and type in `tailwind.config.ts`, a typed client
  mirroring the FastAPI models, and the answer-beside-SQL view. `make web` with
  `make serve` alongside. **Demo beat 1 runs end to end.**
  The approval card (the design plan's signature surface) is Phase 4 and is not
  built. `docs/DESIGN-TOKENS.md` was proposed and then built from — say if the
  palette or type should change and it is a config edit, not a rewrite.
- **Live model path: built, opt-in, and proven against the real model.**
  `DEMO_MODE=false` (`make serve-live`) generates the SQL instead of reading it
  from a file. Every branch is exercised against a stub in CI — no key, no quota —
  and three real Vertex calls (~$0.06) confirmed an answer, a refusal and a
  clerk-scoped query end to end.

**ADR-0001 is resolved — keep generated SQL — but do not cite "two thresholds
fired" any more.** Threshold 3's firing at 10.6% was a sampling artifact: a strict
replication of the same prompt and questions returned 4.3%, and the metric has no
fixed value until the run count is fixed. The resolution's conclusion survives; two
of its three reasons do not. **The canned demo path is still load-bearing** for the
part that does survive, so the live path was added beside it and did not replace it.
Read the ADR's *Review* and *Replication* sections before quoting any of it.

State and corrections: `docs/HANDOFF.md`. Fix-list history:
`evals/FIX-LIST-v2.md`.

## Where things stand

| Phase | Status | Note |
|---|---|---|
| 0 Data foundation | **done** | ~32h against a 20h budget |
| 1 Structured Q&A | **definition of done met; phase not closed** | Both halves done — demo beat 1 runs, live path proven. ADR-0001's three follow-ups are measured and its threshold 3 did not survive replication. Not closed because two instrument decisions are owed a second pair of eyes (whether q017/q049 come out of the silent-wrong count; what replaces threshold 3) and q017/q026's references need fixing or retiring. Budget long overrun; see HANDOFF |
| 2 Corpus ingestion | not started | |
| 3 Document Q&A | not started | |
| 4 Procurement agent | not started | |
| 5 Polish | not started | |

## Last session

_Date:_ 2026-08-08
_What landed:_ The live path, proven live. ADR-0001's three follow-ups, measured.
And **threshold 3 does not survive being measured twice.**

### The measurement, four samples of it

| sample | prompt | questions × runs | not-view-covered | variance |
|---|---|---|---|---|
| first triple, runs 0–2 | `415953…` | 47 × 3 | 88.9% (88/99, CI 81.2–93.7) | **10.6%** |
| **strict replication, runs 3–5** | `415953…` | 47 × 3 | **93.9% (93/99, CI 87.4–97.2)** | **4.3%** |
| pooled, runs 0–5 | `415953…` | 47 × 6 | 91.9% (182/198, CI 87.3–95.0) | 12.8% |
| follow-up | `f3b7a9…` | 49 × 3 | 91.4% (96/105, CI 84.5–95.4) | 2.0% |

**Two triples of the identical prompt over the identical questions returned 10.6%
and 4.3%**, with the 10% decision line between them. The metric is also monotone in
run count, so the six-run pool reads 12.8% by construction. **Threshold 3 has no
fixed value until the run count is fixed, and ADR-0001 never fixed it** — so the
firing that drove the whole resolution was a sampling artifact. What should replace
the threshold is written into the ADR.

- **q017 was never a model failure**, and six runs prove it rather than argue it:
  `wrong ×3, correct ×3` on one prompt. The failures wrote
  `HAVING count(*) FILTER (late) > 0`; the passes wrote
  `HAVING avg(actual) > avg(contracted)`. Two defensible readings of a question
  that never said which — an under-determined question, not an incapable model.
- **The 100% on view-covered was an artifact too.** q032 fails once in six runs;
  65/66.
- **q026 is the one stable failure**, alternating `execution_error` / `wrong_rows`
  across all six runs, never correct. Timeouts are real; its `wrong_rows` disagree
  with a reference `FIX-LIST-v2.md` item 16 already flagged.
- **q036's fix worked: refusal 3/3, up from 2/3 — and q047 stayed correct 3/3**, so
  the causation section did not teach blanket refusal. Context edit, no few-shot
  pair, per the ADR's rule.
- **q049 was mine and is withdrawn.** It scored `wrong_rows` 3/3 while returning
  values numerically identical to its own reference — two labelled rows against one
  row of two columns, 2dp against 1dp. **q050 replaces it**, asked as set
  membership against a stated 25% threshold. Its premise was wrong too: the 7.1s
  timeout I quoted was my own rewrite of the correlated form, not what the model
  writes, which runs in 1.5s.

### Everything else that landed

- **`POST /query` generates SQL when `DEMO_MODE=false`.** `api/src/pos_copilot/live.py`,
  `make serve-live`. Scope reaches the prompt before any SQL exists, the guard
  (rule 4) runs before a connection is opened, and the model's own SQL comes back
  in `generated_sql` beside the wrapped `sql` that ran.
- **Refusals and failures are separate response fields.** `refusal` is the model
  declining (either sentinel); `error` is the guard rejecting the query or
  Postgres refusing it. A failed generated query is a **200 carrying `error`**,
  not a 500 — the request was fine and the system did the right thing.
- **A ceiling, per rule 2.** Process-wide, 50 calls / $1.00 by default, and the
  model call is serialised because `Pacer` and `Budget` are not thread-safe and
  `model.py` is serial by design.
- **`/health` now reports whether live mode can actually serve.** It answered
  `ok` with no credential before, which is this project's defect class in the one
  endpoint whose job is reporting state.
- **The web input is typed, with the catalogue as suggestions**, so the live path
  is reachable from the browser without the UI branching on a mode it is not
  allowed to know (`CONVENTIONS.md`). Provenance is stated per answer from the
  response's own `mode` field.

_Three defects found on the way, two of them mine:_ **`make serve` could not
serve in a shell that had not exported `.env` itself** — `-include .env` makes
*make* variables, not environment ones, so the API got no
`READONLY_DATABASE_URL` and answered every query with a 500 while `/health` still
said `ok`. (Last session's end-to-end check passed because that shell had the
variables; a fresh clone would not have.) `export FOO` for an unset variable
exports it **empty**, so
`int(os.environ.get("LIVE_MAX_CALLS", "50"))` raised on every live request
(`api/src/pos_copilot/env.py` is the fix, and `int("")` was latent in
`resolve_provider` and the eval runner too); and an `OSError` from a rejected key
would have surfaced as a traceback, since urllib's errors are not `RuntimeError`.

**The live path is proven live.** Three real Vertex calls, ~$0.06: net revenue for
May 2026 came back as 8,064,347.42, matching the demo path's figure for the same
month; "how many customers do we have" came back as
`-- INSUFFICIENT SCHEMA: customer data is not tracked in the database`; and a
clerk-scoped question produced `WHERE store_id = 2` in the model's own SQL with the
tripwire silent. `web/` verified serving through the Next rewrite proxy.

_What didn't:_ the approval card (Phase 4). Nothing else was deferred.
_Anything half-finished someone would trip over:_ No. Two gates are live and both
are documented in HANDOFF — `is_active`, and the new `business_date`/`sold_at`
blind spot.
_Is the system in a working state?_ Yes. 230 passed with a database; ruff clean;
`make web-check` clean.

## Next session should

1. **Rule on one judgement, because it changes whether threshold 1 fires.** As
   measured, three distinct questions produced a silent-wrong. q049 is withdrawn
   (mine, and its answer was numerically correct). q017's reference is unverified
   by this project's own stopping rule, and six runs show the model choosing both
   readings. That leaves **q026 alone — and one silent-wrong is "a signal to
   diagnose", not a firing threshold.** Withdrawing a failure is the move that most
   needs a second pair of eyes, so it is recorded in ADR-0001 and not applied.
2. **Decide what replaces threshold 3.** It has no fixed value until the run count
   is fixed. The ADR proposes either a per-question stability rate at an exact run
   count, or measuring the thing the threshold was actually worried about: whether a
   specific answer a reader sees changes between showings.
3. **Fix q017 and q026's references, or retire the questions.** q017 needs to say
   whether "delivers later than contracted" means on average or ever. q026 needs
   its festive window read from the `festivals` table like q024 and q025
   (`FIX-LIST-v2.md` item 16, still unapplied) — and its timeout is a real model
   failure worth keeping as a diagnostic either way.
4. **At the next prompt unfreeze, correct the `business_date`/`sold_at` claim** in
   both context documents, batched so the void is spent once. Details and the
   wording to use are in HANDOFF. It is not urgent: the false claim steers the model
   to the right column anyway.
5. **Review `web/` running** (`make serve` + `make web`). Palette and type are a
   `tailwind.config.ts` edit, not a rewrite.

**Check deliverable against budget before starting**, not at phase close — see
`docs/HANDOFF.md`.

## Measured numbers

_SQL, current prompt `f3b7a9193a56f10d` (n=49 questions × 3 runs, 147 responses):_
not-view-covered **91.4% (96/105, CI 84.5–95.4%)** — the interval still straddles
85% — overall 93.5% (129/138), view-covered 100% (33/33), **cross-run variance
2.0%**, silent-wrong in 3 distinct questions of which one (q049) is withdrawn.
Withdrawing it gives 94.1% (96/102, CI 87.8–97.3%), which clears 85%.

_SQL, previous prompt `415953964db74b80` (n=47, six runs, 282 responses):_
not-view-covered **91.9% (182/198)**, view-covered 98.5% (65/66), variance 10.6%
and 4.3% on its two independent triples, 12.8% pooled. **Do not quote the pooled
interval as if it were tight** — six runs of the same 47 questions are clustered,
so Wilson understates it.

_Attempts-to-correct:_ still not measured; no retry loop exists.

_Extraction:_ Phase 2, not started.
_Injection specimens:_ Phase 3, not started.

## Named debt carried forward

- **`full×3` is done, but it is one sample of three runs.** Variance at 10.6%
  sits right on ADR-0001's line; another triple would move it either way.
- **q036's refusal is not reliable** — two of three. It is the behaviour the
  project's argument rests on.
- **No retry loop exists**, so ADR-0001 threshold 4 has never been measured.
- **On the live path, a scoped query's `WHERE` clause is the model's to write.**
  The scope reaches the prompt carrying the predicate itself
  (`store_id = 1 (Kothrud, Pune)`), and `check_scope` is a tripwire behind it —
  but that tripwire can only fire when `store_id` is among the result columns.
  Pattern-matching the generated SQL for the predicate was deliberately not
  done: that is instance eight's defect (regexes guessing at SQL structure). The
  real fix is a per-store database role, and it is not Phase 1. Demo mode is not
  affected — there the predicate is substituted, not requested.

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
