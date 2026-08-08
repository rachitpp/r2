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

- **Harness: done.** 47 questions × 3 runs against instrument v2.
- **Web app: the query view exists and works.** `web/` is a Next.js App Router
  app with the proposed palette and type in `tailwind.config.ts`, a typed client
  mirroring the FastAPI models, and the answer-beside-SQL view. `make web` with
  `make serve` alongside. **Demo beat 1 runs end to end.**
  The approval card (the design plan's signature surface) is Phase 4 and is not
  built. `docs/DESIGN-TOKENS.md` was proposed and then built from — say if the
  palette or type should change and it is a config edit, not a rewrite.
- **Live model path: built, opt-in, and unexercised against a real model.**
  `DEMO_MODE=false` (`make serve-live`) generates the SQL instead of reading it
  from a file. Every branch of it is exercised against a stub — no key, no quota,
  runs in CI — except the scope tripwire firing on generated SQL, which is tested
  at the `readonly_sql` level rather than through the endpoint. **No call to a
  real provider has ever been made from this code**; that link is wired rather
  than demonstrated.

**Two ADR-0001 thresholds fired and the ADR is now resolved: keep generated
SQL.** The reasoning is in the ADR and is reversible — read it before building
on it. **The canned demo path is load-bearing for that resolution**, so the
live path was added beside it and did not replace it.

State and corrections: `docs/HANDOFF.md`. Fix-list history:
`evals/FIX-LIST-v2.md`.

## Where things stand

| Phase | Status | Note |
|---|---|---|
| 0 Data foundation | **done** | ~32h against a 20h budget |
| 1 Structured Q&A | **definition of done met; phase not closed** | Measurement done (47×3, instrument v2). Query API + web query view working end to end — **demo beat 1 runs**. Live path built, opt-in, never yet called a real model. Not closed because ADR-0001's own three follow-ups remain, and they spend quota — yours to authorise. Budget long overrun; see HANDOFF |
| 2 Corpus ingestion | not started | |
| 3 Document Q&A | not started | |
| 4 Procurement agent | not started | |
| 5 Polish | not started | |

## Last session

_Date:_ 2026-08-08
_What landed:_ The live model path — built against a stub, never yet run against
a model.

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

_What didn't:_ **no live call has ever been made.** The credential resolves and
`/health` reports `vertex / gemini-3.6-flash`, but every test uses a stub, so the
last link is wired and unproven. One call is ~$0.02 and is yours to authorise.
The approval card is still Phase 4.
_Anything half-finished someone would trip over:_ No. The `is_active` gate is
the one live hazard and fires only on a seed change.
_Is the system in a working state?_ Yes. 228 passed with a database; 195 passed
and 33 skipped without one; ruff clean; `make web-check` clean.

## Next session should

1. **Review the ADR-0001 resolution, and overturn it if you disagree.** It was
   resolved by the agent that ran the measurement, which the ADR says outright.
   The load-bearing claim is that demo mode already removes threshold 3's stated
   harm. **q036 is the item to weigh:** the causation refusal held in two runs
   and broke in the third.
2. **Review `web/` running** (`make serve` + `make web`) and the design it was
   built from. Palette and type are a `tailwind.config.ts` edit, not a rewrite.
3. **Fire one live call** (`make serve-live`, ask anything) if you want the last
   link proven. ~$0.02, spends real Vertex quota; everything up to the network
   hop is already tested.
4. **Then one batched quota sitting**, because the cache voids once either way:
   q036's fix in `business_context.md`, the targeted questions for q017 and q026,
   and the **second `full×3`** that ADR-0001 names as what would reverse it.
   ~$0.99 and ~2.3 days at 20 RPD — yours to authorise, per
   `evals/FIX-LIST-v2.md`.

**Check deliverable against budget before starting**, not at phase close — see
`docs/HANDOFF.md`.

## Measured numbers

_SQL (n=47 questions × 3 runs, instrument v2, prompt `415953964db74b80`):_
not-view-covered **88.9% (88/99, CI 81–94%)**, overall 91.7% (121/132),
view-covered 100% (33/33), **cross-run variance 10.6%**, silent-wrong in 5
distinct questions. Attempts-to-correct not measured — no retry loop exists.

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
