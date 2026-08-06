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

1. Write `api/prompts/context/business_context.md` — first, before any prompt
   engineering or eval questions (ADR-0001). **Propose it before writing the
   eval set.** It must teach at minimum: `AS_OF_DATE` not `current_date`;
   signed quantity; out-of-stock vs low-stock; restock defaults to
   `on_hand <= reorder_point`; `business_date` not `sold_at`;
   `valid_period @> DATE 'x'`; every `ORDER BY` needs a tiebreak.
2. Then `evals/sql/questions.jsonl` — 30–50 questions with expected result sets
   computed against `AS_OF_DATE`, each carrying `view_covered`.
3. Then the LIMIT wrapper, then SQL generation, then the Next.js scaffold.
   Design tokens get proposed before any component.

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
- **GST is per category, not a flat rate**: 0% fresh produce, 5% staples/dairy,
  12% packaged foods, 18% household and personal care, 28% aerated drinks. So a
  basket's effective rate is a blend, `sales.subtotal` is net of tax, and
  `total = subtotal + tax_total`. "Revenue" normally means `subtotal`.
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
