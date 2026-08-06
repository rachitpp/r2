# Evals

**Evals measure. Tests assert.** They are different things and live in
different places (ADR-0005). Nothing here gates anything, nothing here runs in
CI, and nothing here is a pass/fail.

This file plays the role `corpus/KNOWN_ISSUES.md` plays for the corpus: it says
what is measured, how, and where the instrument has been wrong. The defects
section is the point of it. An eval set that has never been found wrong has
usually never been used.

    evals/
      sql/questions.jsonl   45 questions + generated expected result sets
      sql/README.md         field-by-field schema and trap coverage
      results/              dated JSON, one per run, with prompt hashes
      .cache/               model responses, gitignored, regenerable

## What the SQL eval measures

Whether generated SQL returns the *right answer* — not whether it runs. A query
that executes cleanly and returns plausible wrong numbers is the failure that
matters, because it is invisible in a demo and an agent will act on it. That is
ADR-0001's first threshold and the reason comparison is on result sets rather
than on exit status.

Reported three ways — overall, view-covered, not-view-covered — and the
threshold is read off **not-view-covered**, because the Phase 0 views answer
some questions almost directly and would flatter the number.

Every figure carries n and a Wilson 95% interval, computed by
`api/scripts/wilson.py`. At n≈40 a five-point difference is not resolvable; see
ADR-0001 for why the set is not being grown to chase one.

## `result_shape`: what the question actually determines

Every question declares the shape of its own answer. This exists because of
defect 1 below.

| Shape | The question fixes | Compared by |
|---|---|---|
| `top_n` | The rows **and** their order, and states the count — "the 10 things we're lowest on" | Ordered exact match |
| `ranked_all` | Every matching row in a meaningful order; the count follows from the data — "rank the days of the week" | Ordered exact match |
| `all_matching` | Every row matching a predicate; order is not meaningful — "what should we reorder at Nashik" | **Multiset equality** against the whole true result |
| `scalar` | A single aggregate row | Ordered exact match |

**`all_matching` is set equality, never containment.** The reference holds every
matching row, with no `LIMIT` of its own. Over-fetching fails, because a loose
predicate adds rows the reference lacks. Under-fetching fails too, because a
model capping at 20 rows where 30 match produces a different set — and an
incomplete answer is a wrong answer. Ignoring the model's `LIMIT` means not
penalising the *clause*. It never means not penalising its *effect*.

A consequence: **an `all_matching` question whose true result exceeds
`SQL_MAX_ROWS` cannot be scored**, because the wrapper truncates the model's
answer and the missing rows are unknowable. Four questions were narrowed for
this reason. `make eval-expectations` refuses to write an expectation that hits
the ceiling.

## Defects found in the instrument

### 1. The reference queries answered questions the questions had not asked

**Found:** 2026-08-06, first staged run against a live model. **Cost:** about
seven model calls. **Severity:** the run scored 0/4 and none of it was the
model's fault.

Every reference query carried a `LIMIT` chosen when it was written. The
questions never asked for one. "What should we reorder at Nashik?" has no
natural answer length, the reference said `LIMIT 20`, and the model said
`LIMIT 100`.

Proof it was the instrument and not the model: on q004, **the model's first 20
rows matched the reference's 20 rows exactly.** It was completely right and was
marked wrong for failing to guess a number that existed only in my file. 17 of
38 scorable questions had this shape, and 19 imposed an `ORDER BY` their
question did not imply.

**Worse, on q001 the reference contradicted the prompt's own rule.** The
question named no store. `sql_generate.md` says that when a question does not
name a store, aggregate across stores. The model did exactly that. The
reference filtered to `store_id = 1` — 139 rows against the correct 440 — so
**the model was scored wrong for obeying the instruction the project gave it.**
That one is worth keeping in view: a reference query is not ground truth simply
because a human wrote it, and it can disagree with the rest of the system.

**Fixed by:** the `result_shape` taxonomy above; putting the count into the
question text wherever the answer is a shortlist; regenerating `all_matching`
references without a `LIMIT`; rewriting q001 to name Pune; narrowing q004,
q005, q006 and q045 to fit under the row cap.

**What it says about method:** an eval set cannot be validated by reading it.
Every one of these questions looked fine on the page. They were only wrong once
a model answered them. Hence the staging gate in `docs/CONVENTIONS.md` — five
questions, one run, failures read by hand, before any full run.

### 2. Truncation was silent

Found while fixing defect 1. The read-only wrapper capped results at
`SQL_MAX_ROWS` and said nothing: 100 plausible rows returned, no error, and in
q006's case 405 rows missing. That is a production silent-wrong, not an eval
artifact — it would reach a user, and an agent would act on it.

`readonly_sql.execute` now fetches one row beyond the cap to know truncation as
a fact, counts the true total when it happens, and returns
`"440 rows matched; showing the first 100."` The extra `COUNT` only runs when
the cap actually bit.

### 3. Column selection and rounding were under-determined too

**Found:** second staged run, same day, five questions that had not been in the
first stage 1 — which is exactly why the rule says to rotate them. Scored 0/5
again, and again almost none of it was the model.

Comparison was on whole row tuples, so a correct answer had to guess three
things the question never fixed:

- **Which columns to select.** 7 of 9 model answers had a different column
  count from the reference. On q014 — "what were our payment terms with X in
  March 2025" — the reference selected `lead_time_days` as well. The model did
  not, because the question did not ask for it. The model's column list was
  arguably the better answer.
- **Column order.**
- **Rounding.** 13 reference queries apply `round()` the question never asks
  for. On q033 the model's `avg` and the reference's `round(avg)` describe the
  same takings and compare unequal.

One genuine model finding survives the noise: on q024 the model looked for a
*promotion* named Holi rather than the festival date window, and returned
nothing. `business_context.md` says Holi appears in March 2025 and March 2026
but never gives the dates, so the window is not knowable from the context it
was given. Per ADR-0001 the fix for that is `business_context.md`, never a
few-shot pair.

**Status: awaiting a ruling.** Proposed direction is to trim every reference to
the columns the question actually asks for, then compare each expected row as a
sub-multiset of the model's row — so extra context columns are free but every
answer value must be present — with a numeric tolerance instead of matched
rounding. That deliberately loosens the instrument, which is a decision worth
taking explicitly rather than by default.

## Running it

    make eval-sql-stub                          # no key, no quota, no network
    make eval-sql EVAL_ARGS="--limit 5"         # the staging gate — required
    make eval-sql EVAL_ARGS="--runs 3"          # the full run

Responses are cached on `(prompt fingerprint, question id, run index)`. The
fingerprint covers `sql_generate.md` and every injected context file, so editing
`business_context.md` invalidates the cache — correctly, since the model would
then be sent something different.

`run_index` is in the key because cross-run variance needs three genuinely
separate responses. Note that with sampling parameters deprecated and ignored
(ADR-0006), that number measures the model's own nondeterminism rather than
prompt instability.
