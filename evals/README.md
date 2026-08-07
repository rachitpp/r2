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

## What four staged runs cost, and what they bought

Three defects. **Every one was found by rotating the questions, not by reading
them.** Every one would have published a confidently wrong number.

| Run | Questions | Score | What it actually found |
|---|---|---|---|
| 1 | q001–q005 | 0/4 | Arbitrary `LIMIT` in every reference; q001's reference contradicting the generation prompt's own store rule |
| 2 | q010, q014, q019, q024, q033 | 0/5 | Column selection, column order and rounding all under-determined; the festival window unknowable from context |
| 3 | q007, q020, q029, q040, q046 | 3/5 | q029 readable as singular; q040's reference demanding a column never asked for |
| 4 | — | pending | The first run whose number can be believed |

Two things are worth sitting with.

**The set had already been reviewed.** All 45 questions were written
deliberately, read back, and cross-checked against independently written second
queries before run 1. Runs 1 and 2 still scored zero. Not one of those defects
was visible on the page; every one needed a model to answer the question before
it appeared. **An eval set cannot be validated by inspection, only by use.**

**Each defect would have produced a confidently wrong number, in the direction
that flatters nobody and misleads everyone.** Run 1's 0/4 read as "the model
cannot write SQL". It was published-quality wrong: had the full 138-call run
gone ahead, ADR-0001's thresholds would have fired, the query catalog would
have been built, and the text-to-SQL approach abandoned on the strength of an
arbitrary `LIMIT 20` in a file nobody would have reread. That is the specific
failure the staging gate exists to prevent, and it happened on the first
attempt.

The rotation rule earned itself immediately: run 2 was chosen to avoid the
questions run 1 had diagnosed, and found a defect class run 1 could not have.
Re-testing what you just fixed proves only that you fixed it.

Total cost of finding all three: **about 20 model calls.**

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

**And it happened twice.** Rotation 4 found q043 the same way: the question
asked for a daily average with no period, the reference quietly filtered to
April onwards, and the model — which used all history — was marked wrong.

> **Twice now a reference has been wrong in the direction of penalising correct
> model behaviour. Two instances is a pattern, and the pattern has a cause: the
> reference author knows what they meant and encodes it without noticing they
> did not say it.**

That is the failure mode to watch for, and it is not fixable by being more
careful — being careful is what produced both. It is fixable only by making a
model answer the question and reading what it did.

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

**Fixed by** comparing each expected row as a **sub-multiset** of the model's
row. Rows are the answer; columns are a projection over it. Extra columns
cannot make an answer wrong — returning the supplier name alongside the payment
terms has still answered the question — but a missing one can. Over-selection
is not entirely unmeasured: reaching for a column the read-only role cannot see
fails at the permission layer instead.

## The family, audited rather than patched one at a time

All three defects were the same thing: **the reference encoded a choice the
question did not determine.** Rather than fix the third instance, the whole
family was enumerated on paper — no model calls — and closed at once.

| Under-determined | Status | How it is handled |
|---|---|---|
| Row count (`LIMIT`) | **was live** | `result_shape` |
| Row order | **was live** | `result_shape` |
| Column selection | **was live** | sub-multiset row match |
| Column order | **was live** | sub-multiset row match |
| Column names (`weekday` vs `day_of_week`) | latent | values compared, names never |
| Rounding / precision | **was live**, 13 questions | precision alignment + tolerance |
| Numeric vs text rendering of a number | latent, 32 questions | parsed as `Decimal` |
| Padded `to_char` output (`'Sunday   '`) | **was live**, q033 | trimmed before comparison |
| Boolean rendering (`t` / `true` / `TRUE`) | latent | normalised |
| date vs timestamptz vs text, timezone in rendering | latent, 6 questions | compared as the day only |
| `NULLS FIRST` vs `NULLS LAST` in an ordered shape | **absent today** | guarded by test |
| Ties at a `top_n` cutoff | **absent today** | guarded by test |
| A `GROUP BY` the question did not ask for | not under-determined | changes the rows, so it correctly fails |

The last two are clean right now and guarded rather than fixed, because they
are properties of the seeded data and could reappear when it changes.

### A third axis, found in rotation 4: the predicate itself

The table above is all *presentation* — how the same rows are counted, ordered,
projected and rendered. Rotation 4 found the family has another axis, and it is
worse, because loosening comparison cannot fix it.

**A time window, a threshold or a join rule that the question does not state is
a choice the model has to guess, and it changes which rows exist.**

- q043 asked "how many transactions on an average day" with no period. The
  reference quietly filtered to April onwards; the model used all history. The
  model was arguably more right.
- q031 asked for the worst-margin lines "that still sell well". The reference
  defined that as `HAVING sum(net_units) > 500`. Nothing in the question does.
- q035 asked "did our promotions lift sales". The reference inner-joined, so
  only the 32 promotions with sales appeared; the model included all 46.

**These can only be fixed in the question.** Six questions were reworded to
state their period or threshold outright — "since the start of April", "among
those that have sold more than 500 units", "that had any sales". A question
that does not determine its own answer cannot score one, and a predicate is
part of determining it.

## Tolerance

**Absolute, never relative.** The returns trap is a 0.3% gap — 54,759 gross
units against 54,594 net — and any relative tolerance loose enough to be useful
would swallow it, reporting a pass on the exact failure it exists to catch.

    counts, quantities, ids     exact
    money                       +/- 0.01     (matches corpus/README.md)
    rates, percentages          +/- 0.005

Kind is derived from the reference column's name. `margin` is money;
`margin_pct` is a rate.

**Values are compared at the coarser of the two precisions**, then within
tolerance. This is not a loosening — it is the same under-determination one
level down. "Rank the days by average takings" never says how many decimals, so
a reference writing `round(avg(...))` gives 326958 where a raw average gives
326958.0876: the same answer, 0.0876 apart, which absolute money tolerance
alone would call wrong. Alignment is on *decimal places*, not significant
figures, so a model answering 1200 where the truth is 1234.56 still fails.

`api/tests/test_tolerance.py` holds the right-and-known-wrong pair for every
trap and asserts each gap clears its tolerance by more than an order of
magnitude. **If a tolerance is ever loosened to within 10x of a trap gap, that
test fails** — the trap would otherwise stop being a trap silently.

### A sixth axis, found in rotation 5: questions that ask for what data cannot hold

q036 asked which top sellers "were only top sellers **because** they were
discounted". The model refused:

> `-- INSUFFICIENT SCHEMA: baseline demand model or counterfactual sales data`
> `to determine if a product's top-seller status was caused by promotional`
> `discounting`

That refusal is correct. The question asks for causation; the data supports
correlation. The reference quietly answered a **proxy** — share of units sold
on promotion — and passed it off as the answer, so the model was scored wrong
for noticing the substitution.

This is not the predicate axis. The predicate axis is a question that does not
say *enough*. This is a question that asks for something the data cannot hold
at all, where the reference substitutes something it can and does not say so.
Reworded to ask what the data actually supports.

### What the instrument was actually measuring

> **The instrument measures whether the model guesses the author's intended
> answer, not whether it understands the data. Rotation is the post-hoc fix;
> inverting the authoring order is the preventive one.**

The bias has a direction, and that is what makes it systematic rather than
noisy. Four references were wrong before the measured run — q001, q017, q043,
q045 — and **every one was wrong in favour of the reference and against the
model.** Not one erred the other way. A random defect would scatter; this one
points, because the author knows what they meant and it therefore looks obvious
in retrospect.

> **The 47×1 run made this much larger, and the direction did not change.**
> Diagnosis found **11 of 14 failures to be instrument defects** — and again,
> not one erred against the reference. See
> [`DIAGNOSIS-2026-08-07.md`](DIAGNOSIS-2026-08-07.md), which also carries
> **three axes beyond the six below**, one correction to this section, and a
> falsified verification found in its own record:
>
> - **Axis 7 — row identity.** Which column names a row is not determined by
>   the question: `stores.code` and `stores.name` both identify it. First
>   written up as "free-text labels the query invents"; **that statement was
>   wrong and its evidence was wrong in 3 of its 4 questions.** Corrected there.
> - **Axis 8 — ratio magnitude.** "Share" does not determine `0.05` or `5.0`.
> - **Axis 9 — disambiguation was unscoreable.** It was scored on stated
>   reasoning that `sql_generate.md` forbids the model from writing. Ruled:
>   a reading is read off the predicate, not the caption.
>
> Also corrected there: **q043's `reference_sql` was never edited.** What
> rotation 4 fixed was its *question*, which had not named the period the
> reference filtered on.

### The systematic gap behind all six

Six axes is no longer a series of individual oversights, and the common cause
is structural rather than careless:

> **Every question and its reference were written by the same person, in the
> same sitting, with the intended answer already in mind.** The reference
> therefore encodes the author's private reading of the question, and the only
> check on it was that same author — who shares the reading, so cannot see it
> is missing from the words.

Being more careful cannot fix this, because care is what produced it. The
authoring path itself is wrong. What works is exactly what rotation does: put
the question to something that does not already know the intended answer, and
treat disagreement as evidence about the *question*.

The proposal that follows is to invert the order for any future question —
**question, then model answer, then sharpen the question, and only then write
the reference.** Rotation currently applies that test five at a time, after the
fact. Applied at authoring time it is the same test, run before the reference
can absorb the assumption.

## Inverted authoring

Applied 2026-08-07 to the 21 questions rotation had not yet spent, plus q047.
**Question first, model answers, sharpen the question against what it did, and
only then trust the reference.** Zero added cost: the calls would have been
spent on rotation anyway.

22 calls. **Not a measurement** — the references were in flux during the pass,
so no accuracy figure from it is recorded anywhere. A number in a file becomes a
baseline somebody compares against later.

12 agreed outright. Of the 9 disagreements, **8 were the question, not the
model** — "fast-moving" never defined, no period stated on a GST
comparison, no grain stated on a stock valuation, "top sellers" left open.
Six questions were sharpened, one reference corrected (q012 invented a
`stockout_days >= 3` filter the question never mentioned), and q027 became a
`disambiguation` because the ambiguity between raw festive revenue and
uplift-against-own-baseline *is* the trap and cannot be scored as a fixed
result set.

That ratio is the argument for the inversion. Eight defects that would each
have surfaced one rotation at a time, five calls apart, were found in a single
pass — and found *before* the reference hardened around them.

### The sharpened questions went into the context document, not just the eval

Sharpening a question fixes the measurement and can leave the *product*
ambiguous — the ambiguity moves out of the eval and into the gap between eval
and reality. A manager in the demo will say "fast-moving" and will not say
"selling more than 2 a day".

So every definition introduced by sharpening was also added to
`business_context.md`: what fast-moving, slow-moving, top seller, about to run
out and running low mean, with the number and why that number; plus two
defaults, that stock questions are per store and that an unstated period means
all available history, named. Thresholds are anchored to the seeded
distribution rather than invented — "more than 1 a day" is the top quartile,
and a "more than 1,000 units" definition of top seller was rejected because it
would name 264 of 600 products.

## When to stop rotating

"One more rotation" has no natural end, so the rule is:

> **Every question must be model-tested, and the instrument corrected against
> it, before measurement** — by rotation, by inverted authoring, or by any
> mechanism that puts a model's disagreement in front of the author before the
> reference hardens.

The earlier form of this rule was "stop when a rotation finds no new defect
class", which is the same rule stated by its symptom. Coverage is the point;
rotation was only ever the means.

So a rotation with nothing left to draw on is **coverage complete, not a gap**.
Do not manufacture questions to satisfy a rule whose purpose is already served.

While a rotation is still the mechanism: a rotation scoring 3/5 where all three
are genuine model errors in covered categories is clean; 4/5 where the single
failure reveals a new axis is not. A sixth axis means asking whether the set has
a systematic design gap rather than a series of individual ones — which is what
happened, and what the inversion answers.

### Fresh-question ledger

A rotation run on a question the model has already been tuned against measures
nothing, so questions are spent once. **20 of 46 spent, 26 left — five rounds
at five a round.**

| Rotation | Questions | New defect class found |
|---|---|---|
| 1 | q001 q002 q003 q004 q005 | Arbitrary `LIMIT`; reference contradicting the prompt's store rule |
| 2 | q010 q014 q019 q024 q033 | Column selection, order, rounding; festival window unknowable |
| 3 | q007 q020 q029 q040 q046 | Singular-vs-ranked reading; unasked-for column demanded |
| 4 | q013 q021 q031 q035 q043 | **Predicate axis** — unstated period, threshold, join rule |
| 5 | q009 q017 q026 q036 q045 | **Causal-question axis** — question asks what the data cannot hold; reference substitutes a proxy |
| 6 | — | pending; 21 unspent questions went through inverted authoring instead |

Unspent (21): q006 q008 q011 q012 q015 q016 q018 q022 q023 q025 q027 q028 q030
q032 q034 q037 q038 q039 q041 q042 q044.

**25 of 46 spent.** Five rotations, six defect classes, ~30 model calls.

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
