# SQL eval set

43 questions in `questions.jsonl`, one JSON object per line.

**Evals measure; they do not assert** (ADR-0005). Nothing here runs in CI or in
pytest — except a staleness check, which costs no quota because it makes no
model call.

## Fields

| Field | Meaning |
|---|---|
| `id` | `q001`… Stable; do not renumber. |
| `question` | The natural-language question, as a manager would ask it. |
| `intent` | What a correct answer must contain. The scoring rubric for the non-`rows` cases. |
| `expects` | `rows`, `empty`, `refusal`, or `disambiguation` — see below. |
| `view_covered` | Whether one of the Phase 0 views answers this more or less directly. |
| `tags` | Topic labels. |
| `traps` | Named failure modes this question is built to catch. |
| `note` | Why the question exists, where that is not obvious. |
| `twin` | On a refusal: the id of its answerable counterpart. Every refusal has one. |
| `reference_sql` | Hand-written ground-truth query. `null` for refusals and disambiguations. |
| `expected` | Result set, **generated** by executing `reference_sql`. Never hand-edited. |
| `seed_fingerprint` | Ties the expectation to the seed it was computed from. |

## The four expectation kinds

- **`rows`** (37) — a definite result set. Scored by comparing result sets, not
  by whether the query ran (ADR-0001, threshold 1).
- **`empty`** (1) — zero rows is the *correct* answer. This is a separate kind
  on purpose: an empty expectation filed under `rows` would score every wrong
  query as correct, so the reference query for a `rows` question returning
  nothing is treated as a broken question and fails the build.
- **`refusal`** (3) — the honest answer is `-- INSUFFICIENT SCHEMA`. Asking for
  something the data cannot support, or that the read-only role cannot see.
- **`disambiguation`** (2) — the question is genuinely ambiguous. Scored on
  whether the answer *states which reading it took*, not on which reading.

**Every refusal is paired with an answerable twin**, named in its `twin` field
and enforced by a test. A refusal standing alone teaches refusal of the whole
shape: q023 declines a Diwali-over-Diwali comparison while q024 answers the
same question about Holi, so what is learned is a judgement about the window
rather than "decline festival comparisons". Likewise q037/q042 — refuse to name
a cashier, answer the same concern at pattern level, per ADR-0002 — and
q038/q043, where there is no customer table but baskets are countable.

## `view_covered` and why it exists

11 of 43 questions are close to `SELECT * FROM <view> WHERE …`, because Phase 0
shipped views that encode the metric definitions. Those questions measure the
view, not the model.

**The ADR-0001 threshold is evaluated against the not-view-covered number.**
Reporting only the overall figure would flatter the result and could keep
generated SQL alive when the measurement should have killed it. See ADR-0001,
"The measurement has to survive its own convenience layer".

## Regenerating expectations

    make db            # rebuild the database from the committed seed
    make eval-expectations

`expected` is generated, never typed. A hand-written result set is a second
thing that can be wrong, and a wrong expectation turns every score into noise.

Expectations are pinned to the seed by `seed_fingerprint`. Regenerating the
seed invalidates all of them — a pytest fails until they are recomputed.

## What the questions are built to catch

Drawn from what a manager asks, then checked to make sure the hard cases are
represented rather than the ones the schema makes easy:

| Trap | Questions |
|---|---|
| Out of stock vs low stock vs below reorder point | q001, q002, q003 |
| An explicit number overriding the reorder point | q005 |
| Signed quantity — `SUM(quantity)` is net, not gross | q007, q008, q009 |
| Stockouts understating the velocity of fast movers | q010, q011, q012 |
| Point-in-time lookup vs the current value | q014, q016, q021 |
| Contracted lead time vs actual delivery | q017 |
| Blending a tax rate across the 22 Sep 2025 GST reform | q018, q019, q022 |
| A year-on-year comparison the window cannot support | q023 (vs q024, which can) |
| Store size confounding a store comparison | q027 |
| Revenue meaning net of tax | q028 |
| Promotions inflating a best-seller list | q035, q036 |
| Pattern-not-people: staff identity is not readable | q037 |
| Transactions are not customers | q038 |
| Empty being a real answer | q041 |
| Pattern level answerable where person level is not | q042 |
| Baskets are countable, customers are not | q043 |
