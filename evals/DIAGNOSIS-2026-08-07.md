# Diagnosis of the 47×1 run — 2026-08-07

Prompt `de60dd5e3dde7787`. Seed `206fb7a8e55164f9`. Zero model calls: every
response was already cached.

**Raw:** 69.7% not-view-covered (23/33, 95% CI 53–83%). That figure is **not a
verdict** and is not reported anywhere without this file beside it.

## Rules this file follows

1. **Bucket and reasoning are written before checking whether the bucket moves
   the score.** The pull toward "instrument" on a failure and "fine" on a pass
   is strong and invisible from inside.
2. **A question I have not actually examined is marked `undiagnosed`.** Not
   assigned a likely bucket. Fourteen careful diagnoses reported as fourteen is
   worth more than forty-seven reported as forty-seven.
3. Instrument fixes are **capped at 10 per round**. Beyond that it is a
   different instrument and the run is void — which is fine, deliberately, but
   never by accumulation.

## Buckets

| Bucket | Meaning |
|---|---|
| `instrument` | Reference wrong, question under-determined, or comparison too strict. Model right or defensibly right. |
| `context` | Model wrong, but `business_context.md` did not give it what it needed. ADR-0001 says fix the context document. |
| `model` | Context sufficient and available. Model still wrong. |
| `ambiguous` | Two genuine readings. |

---

## A seventh axis: free-text labels the query invents

Found while diagnosing, and it is the largest single cause in the failure
column.

**q019** asked for the effective tax rate before and after the reform. The
model returned:

| | reference | model |
|---|---|---|
| label | `before` | `Before Sep 22, 2025` |
| rate | **8.23** | **8.23** |
| label | `from 22 Sep 2025` | `From Sep 22, 2025 onwards` |
| rate | **6.73** | **6.73** |

**Identical numbers. Scored wrong on the label text.**

A `CASE … THEN 'before'` label is a string the query *invents*; the question
never specifies its wording. This is the same class as column names — which are
already ignored, because comparison is on values — except that a label *is* a
value, so it gets compared.

The distinction that matters: a weekday from `to_char`, a festival name from
`festivals`, a supplier name from `suppliers` are **data**. A period label in a
`CASE` expression is **presentation**.

Confirmed to fully explain q019, q022, q024 and q042 — 4 of 14 failures.

**Fix (counts as 1 of the 10):** questions whose answer distinguishes rows by an
invented label move to an ordered shape, and the label leaves `answer_columns`.
Order carries which row is which, instead of a string the model must guess.

---

## Failures — diagnosed

| id | bucket | reasoning |
|---|---|---|
| q019 | `instrument` | Numbers identical (8.23 / 6.73), verified by hand against the database. Label text only. |
| q022 | `instrument` | Re-scored correct once the invented label is ignored. |
| q024 | `instrument` | Same. Festival label formatting. |
| q042 | `instrument` | Same. Store label formatting. |
| q026 | `model` | Correlated `EXISTS` inside aggregate `CASE`, three times over. 1.59s where the reference is 0.10s; compounds past the 5s statement timeout. Semantically plausible, operationally unusable. The context document cannot teach query planning, and nothing about the question invited that shape. First unambiguous model failure. |
| q004 | `ambiguous` | Question names an explicit cover threshold ("less than three days"). Model used `on_hand > 0`; reference also required `below_reorder_point`. `business_context.md` says restock questions default to the reorder point, but it does not say whether an explicit threshold *replaces* that default or *adds* to it. Both readings defensible. **Context gap on the interaction between an explicit threshold and the default** — candidate for a context fix rather than a question fix. |

## Failures — undiagnosed

**q011, q012, q015, q031, q035, q045, q047.** Seven remain. Each needs the
model SQL executed and compared field by field, which is work, not guesswork. No
bucket assigned.

## Needs-review — diagnosed

| id | bucket | reasoning |
|---|---|---|
| q018 | **model passed the trap** | The blended-rate trap. The model split at 22 September unprompted and labelled both periods. That is the correct behaviour, and it is the single most encouraging result in the run — the GST reform teaching in `business_context.md` worked. Scored `needs_review` because `disambiguation` cannot be auto-scored; by eye it is correct. |
| q003 | `undiagnosed` | Model used `below_reorder_point` and did not state which reading of "needs attention" it took. Whether it stated its reading needs the prose answer, not the SQL. |
| q027 | `undiagnosed` | Same shape. |

## Passes — audited

| id | bucket | reasoning |
|---|---|---|
| q001 | `instrument` | **Passed by an unsound route.** Model omitted `below_reorder_point`; ordering by ascending cover and taking 10 happens to surface the same rows. Shift the data and the answers diverge. Also reveals a fifth reference-author error: the question never mentions the reorder point, so the reference encoded an unstated assumption. **A pass hiding a defect in both directions.** |
| q007, q013, q016, q020, q021, q030, q040, q046 | `sound` | Read by eye. Correct answers by defensible routes. q020 joins `gst_rates` twice at either side of the reform date rather than walking the supersedes chain — different from the reference and arguably better. |

## Passes — unaudited

**21 of 30 passes have not been read.** At the observed rate — 1 unsound in 9
sampled — roughly 2 more are expected to be hiding something. Not extrapolated
into any number; stated so the gap is visible.

---

## What is established so far

- **4 of 14 failures are instrument**, all one newly-found axis.
- **1 of 14 is unambiguously model** (q026).
- **1 of 14 is a context gap** (q004) — exactly the kind ADR-0001 says to fix in
  the context document.
- **1 needs-review is a model success** on the hardest trap in the set (q018).
- **1 of 30 passes was unsound** (q001), and it also exposed a reference error.
- **7 failures and 21 passes remain undiagnosed.**

The temporal cluster prediction is **partially borne out but not for the
predicted reason**: q019, q022 and q024 are all temporal and all failed — but on
label text, not on point-in-time reasoning. q015 is temporal and still
undiagnosed. So the "does `business_context.md` teach *when* a question implies
point-in-time rather than current-state" question is **still open**, and is the
most valuable remaining thing to answer.

## Fix budget for this round

Used: **1 of 10** — the label axis.

Not yet spent, pending the remaining diagnoses. Fixing before the diagnosis is
complete would change the instrument mid-audit and void the comparison.

## Note on runs 1 and 2

If diagnosis changes `business_context.md`, the run-0 prefix is void and gets
re-spent. That is the argument for finishing diagnosis **before** buying runs 1
and 2, not after.
