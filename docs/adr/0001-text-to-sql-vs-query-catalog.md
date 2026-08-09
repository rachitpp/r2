# ADR-0001: Text-to-SQL, with measured thresholds for switching to a query catalog

Date: 2026-08-05
Status: **Resolved 2026-08-08 — keep generated SQL.** The resolution was recorded
on a single triple where two thresholds fired. A strict replication of that same
prompt and question set has since returned **4.3% variance against the 10.6% that
fired threshold 3**, and the reasoning has been reviewed by a later session: the
conclusion stands, **two of its three stated reasons do not**, and threshold 3
turns out not to be a well-defined quantity. Read "Review of this resolution" and
"The replication" before citing any number from "The resolution".

## Context

The first design review recommended replacing open-ended text-to-SQL with a
curated catalog of ~25–40 parameterised queries. A later audit of the numbers
behind that recommendation weakened it substantially, and the audit is the
reasoning here — not a footnote.

**What the audit found.** The Spider 2.0-Lite figures cited in support ("69.65%
top performer", "30–36%") came from a semantic-layer vendor's blog and were a
misreading of a fragmentary snippet. Worse, they were applied to the wrong
difficulty regime: Spider 2.0-Lite is 547 problems across 150+ databases
averaging ~800 columns, with multiple SQL dialects. This project's schema is
~15 tables. The better analogue is classic Spider, where DAIL-SQL with GPT-4
reached 86.2% execution accuracy in 2023. Reported Spider 2.0-Lite scores have
also moved fast — roughly 30% in early 2025, 60%+ with recent frontier models,
71.84 posted on the leaderboard in April 2026 — so any single snapshot is stale
on arrival.

The dbt Labs semantic-layer benchmark was also load-bearing in the original
argument, and dbt Labs sells a semantic layer. The corroborating source (Atlan)
sells a metadata catalog. The one independent, peer-reviewed data point cuts
differently: a JAMIA Open study found GPT-4 at 8.3% accuracy with schema alone
versus 78.3% with a business-context document, and narrowing the schema *without*
that document only reduced failure to 50%. **The context document was doing the
work, not deterministic query generation.**

## Decision

Use generated SQL against a documented schema. Write the business-context
document and schema documentation *before* any prompt engineering — it is the
highest-return work available. Measure on this schema with a 30–50 question eval
set, each question run 3x, and switch to a query catalog only if measurement
demands it.

## The measurement — 2026-08-08, instrument v2, 47 questions x 3 runs

Prompt `415953964db74b80`, seed `206fb7a8e55164f9`, 141 responses, ~$2.79 total.

| | result | threshold | fires? |
|---|---|---|---|
| **1 · silent-wrong** | **5 distinct questions** — q016, q017, q026, q036, q043 | two or more | **YES** |
| **2 · execution accuracy** | not-view-covered **88.9% (88/99, CI 81–94%)** | interval must exclude 85% | no — straddles, and the estimate is above it |
| **3 · cross-run variance** | **10.6%** | > 10% | **YES**, narrowly |
| **4 · attempts-to-correct** | not measured — no retry loop exists | > 1.3 | n/a |

Five questions changed outcome between identical runs:

    q016   wrong_rows  -> correct     -> correct
    q022   exec_error  -> correct     -> correct
    q026   exec_error  -> wrong_rows  -> exec_error
    q036   correct     -> should_have_refused -> correct
    q043   correct     -> wrong_rows  -> wrong_rows

**Read threshold 1 before acting on it.** It says every silent-wrong is
investigated individually and that the investigation is the INPUT to the
decision, not a step after it. All five are now **model** failures — the
instrument defects that produced the original 23/33 have been fixed and
re-scored, and that correction was worth six questions with the model held
completely fixed. But two of the five are *not stable failures*: q016 and q043
each passed in at least one run.

**q036 is the one to sit with.** It is the causation trap — the question the
data cannot answer — and the refusal held in two runs and broke in the third.
A refusal that is right two times in three is not a safety property.

**Threshold 3 fires at 10.6% against a 10% line.** That is inside the noise a
three-run sample can resolve, and the honest reading is "at the boundary,
measured once" rather than "decisively over".

## The resolution — keep generated SQL

Two thresholds fired and the catalog is **not** being built. Three reasons, in
order of weight.

**1. Threshold 3's stated harm does not apply to the demo, because demo mode
already removed it.** The threshold reads *"non-determinism is fatal for a
repeated demo"* — the harm is a demo that answers differently each time it is
shown. `POST /query` in demo mode answers from `api/demo/queries.json` with
**zero model calls**, so the demo is deterministic by construction. The variance
is real and it lives on the live path, which is a labelled capability a reader
opts into with their own credentials. The threshold fired at 10.6% against a 10%
line on a single triple; one question either way moves it to 8.5% or 12.8%.
Firing by 0.6 points on one sample, against a harm that has already been
designed out, is not enough to discard the premise of the project.

**2. Threshold 1's own instruction is to investigate individually, and the
investigation does not describe an incapable model.** Of the five distinct
silent-wrongs, **three pass in at least one run** — q016 dropped `sku` from a
SELECT, q043 chose `subtotal` over `total`, q036 answered instead of refusing.
Those are instability, not inability. Two fail consistently and are specific:
q017 reads `po.expected_on` instead of the terms in force at order time, and
q026 writes a correlated `EXISTS` that exceeds the statement timeout. Both are
exactly what this ADR says to respond to with **targeted questions probing the
observed failure mode**, and neither is evidence that generated SQL cannot work
on a fifteen-table schema.

**3. Threshold 2 — the one that measures capability — does not fire.**
88.9% with an interval of 81–94%, above the line rather than below it, and
100% on view-covered questions. The audit that opened this ADR predicted the
context document would do the work, and it did.

### What is being done instead

- **q036 gets its own work, and it is the real finding.** The causation refusal
  held twice and broke once. That is a safety property, not an accuracy metric,
  and it is the behaviour this project's argument rests on. Per this ADR's own
  rule, the fix is `business_context.md` — **not** a few-shot pair showing the
  refusal, which would destroy the instrument while appearing to improve it.
- **Targeted questions for q017 and q026**, being the two consistent failures.
- **The demo path stays canned.** That is now load-bearing for this decision
  rather than merely convenient, and it should not be replaced with live
  generation without revisiting this ADR.

### What would reverse this

**A second full×3 putting cross-run variance clearly above 10%**, or q036-class
refusal instability appearing in other refusal questions. The first is one run
away and cheap; nothing here should be treated as settled until it exists. This
resolution rests on 10.6% being a boundary reading of one sample — if it is not,
the resolution changes.

**Recorded by the agent that ran the measurement**, which is worth stating: the
project's rule is not to act on a number on first sight of it, and the mitigating
fact is that the reasoning above turns on demo mode's design rather than on the
number itself.

> **This reversal test could not have fired.** Responses are cached on
> (prompt fingerprint, question id, run index) and the runner iterated run
> indices 0…runs-1, so re-running `--runs 3` under an unchanged prompt replays
> runs 0–2 from cache, makes **zero calls**, and reports 10.6% back as
> confirmation of 10.6%. The condition named here was a check that could not
> fail, wearing the label of one that could — the ninth instance of this
> project's recurring class, and it was written into the reversal test of its
> most consequential decision. Fixed 2026-08-08: `--run-offset` exists, and the
> runner now says out loud when a multi-run scoring made no calls.

### Review of this resolution — 2026-08-08, a later session

Requested explicitly, and the ADR asked for it. **The decision survives; two of
its three reasons do not.**

**Reason 1 proves too much, and should carry no weight.** If demo mode's
determinism answers threshold 3, it answers all four: a canned path cannot
produce a silent-wrong either, so thresholds 1 and 2 would be equally
disarmed — and then the thresholds measure nothing, which cannot be what they
were for. They exist to decide whether *generated SQL* is trustworthy, and the
demo's determinism is orthogonal to that question. Worse, the mitigation and the
verdict have the same author in the same sitting: demo mode was built hours
before it was cited as the reason a threshold did not matter. That is not
"designed out before the threshold fired", it is a defence constructed alongside
the thing it defends.

**"Clearly above 10%" is a bright line softened after seeing the number.** The
threshold reads `> 10%`. It was met. Restating the reversal condition as
*clearly* above 10% — after 10.6% came in — is the instrument loosening that
this project polices everywhere else, in the one place where the loosening favours
the decision already taken. The honest version is the original: `> 10%` on a
second triple.

**Reason 3 reports an inconclusive result as support.** This ADR's own text says
a straddling interval "supports no decision at all". 88.9% (81.2–93.7%) straddles
85%, so it is not evidence *for* keeping generated SQL; it is an absence of
evidence against. The resolution wrote it as "above the line rather than below
it", which is the point estimate doing work the ADR forbids it from doing.

**Reason 2 is the one that holds** — and the 2026-08-08 follow-up measurement
strengthens it while changing what it rests on. See the section below: q036's
refusal now holds 3/3, and of the two "specific and addressable" consistent
failures, **q017 turns out not to have been a model failure at all.**

**What the review does not dispute:** building a catalog would trade a measured
number for an unmeasured coverage ceiling, and the audit that opens this ADR
predicted the context document would do the work — which the follow-up confirms
twice over, since both fixes that moved the numbers were context fixes. Keep
generated SQL. Just keep it for reason 2 and for that, not for reason 1.

## The follow-up measurement — 2026-08-08, prompt `f3b7a9193a56f10d`

The three things this ADR said it would do instead of building the catalog, done
and measured in one sitting because each of them voids the cache anyway. 49
questions × 3 runs, 147 calls, ~$3.32.

| | first measurement | follow-up | fires? |
|---|---|---|---|
| **1 · silent-wrong** | 5 distinct | **3 distinct** — q017, q026, q049 | **YES**, as measured |
| **2 · execution accuracy** | 88.9% (81.2–93.7%) | **91.4% (96/105, CI 84.5–95.4%)** | no — still straddles 85%, by half a point |
| **3 · cross-run variance** | 10.6% | **2.0%** (1 of 49) | **NO** |
| **4 · attempts-to-correct** | unmeasured | unmeasured — still no retry loop | n/a |

**q036's fix worked, and did not over-refuse.** The causation refusal held **3/3**
where it was 2/3, and **q047 — the answerable twin the fix could have destroyed —
stayed correct 3/3.** The fix was a `business_context.md` section stating what
these tables cannot show, and it was written to list the associations that *are*
answerable precisely so it could not teach blanket refusal of promotion questions.
Per this ADR's own rule, no few-shot pair was added.

**Threshold 3 stopped firing, and what moved is worth reading.** Four of the five
formerly unstable questions — q016, q022, q036, q043 — are now stably **correct**,
so the drop is not failures becoming consistent. Whether it is the prompt or the
noise in a three-run statistic is not something this run can distinguish, which
is why a strict replication of the *previous* prompt at `--run-offset 3` follows.

**q017 was not a model failure.** Two defects were stacked under it:

1. **The schema documentation was false, and it licensed the failure.**
   `purchase_orders.expected_on` was documented as "the delivery date promised at
   ordering, from the supplier's contracted lead time". Every order in the dataset
   carries `ordered_on + the supplier's CURRENT lead time` — including all 7,905
   placed *before* that supplier renegotiated — so for **5,329 of 15,723 orders**
   it disagrees with the terms in force on `ordered_on`. Measured against
   `expected_on` every supplier looks late by about 0.9 days; measured against
   what they actually contracted to, **seven of twelve delivered early.** Same
   data, opposite conclusion. A model reading that comment and using `expected_on`
   was following the documentation.
2. **With the comment corrected, the question is still under-determined.** q017 now
   joins `supplier_terms` on `valid_period @> ordered_on` and never touches
   `expected_on` — and still fails 3/3, because the reference reads "deliver later
   than the lead time they contracted to" as *average actual > average contracted*
   while the model reads it as *at least one late delivery*. The question does not
   say which. By this project's own stopping rule — a reference is verified when
   every predicate **and its grain** traces to specific words in the question —
   q017's reference is unverified.

**q048 confirms that reading.** The targeted question written for q017's failure
mode, which names the period explicitly, passes **3/3**. The model can read
terms-in-force; q017 was not testing whether it could.

**q049 is withdrawn: the defect was in the question, and it was mine.** It failed
3/3 as `wrong_rows` while returning **numerically identical** values to its own
reference — the model gave two labelled rows where the reference gives one row of
two columns, and rounded to 2dp instead of 1dp. Row identity and rounding: axes 7
and 3 of the instrument audit, written fresh into a question added to probe someone
else's failure. Its stated premise was also wrong — the 7.1s timeout was measured
on *a rewrite* of the correlated form, not on what the model writes, and the
model's own formulation runs in 1.5s. q050 replaces it, asked as set membership
against a stated threshold so it cannot fail on shape.

**So threshold 1's status is now a judgement, not a count.** As measured it fires
on three distinct questions. Of those, q049 is withdrawn and q017's reference is
unverified by the project's own rule, which leaves **q026** — whose two failures
are statement timeouts, and whose one `wrong_rows` disagrees with a reference that
`evals/FIX-LIST-v2.md` item 16 already flagged for hardcoding a festive window
that q024 and q025 read from the `festivals` table. **One silent-wrong is a signal
to diagnose, not a firing threshold.** Withdrawing a failure is exactly the move
that needs to be visible rather than quiet, so it is recorded here and left for
the next session to accept or reject.

**The direction has not changed once.** Nine axes of instrument defect, and every
single one favoured the reference and ran against the model. Two more today: a
false schema comment, and a question of mine that scored a correct answer wrong
three times.

## The replication — 2026-08-08, and threshold 3 does not survive it

Requested as a strict replication: **the same prompt `415953964db74b80`, the same
47 questions, run indices 3–5**, so nothing was replayed. 141 calls, ~$2.99,
**0 cache hits.** The pre-fix `business_context.md` and `schema.md` were restored
from git and the fingerprint was verified to recompute to `415953964db74b80`
before anything was spent.

| sample | prompt | questions × runs | not-view-covered | variance |
|---|---|---|---|---|
| first triple, runs 0–2 | `415953…` | 47 × 3 | 88.9% (88/99, CI 81.2–93.7) | **10.6%** |
| **replication, runs 3–5** | `415953…` | 47 × 3 | **93.9% (93/99, CI 87.4–97.2)** | **4.3%** |
| pooled, runs 0–5 | `415953…` | 47 × 6 | 91.9% (182/198, CI 87.3–95.0) | **12.8%** |
| follow-up | `f3b7a9…` | 49 × 3 | 91.4% (96/105, CI 84.5–95.4) | **2.0%** |

**Threshold 3 is not a well-defined quantity, and that is the finding.** Two
triples of the *identical* prompt over the *identical* questions returned 10.6%
and 4.3% — a factor of 2.5 apart, with the decision line sitting between them.
One triple fires the catalog decision and the other does not, and nothing
distinguishes them but the draw.

It is also **monotone in the number of runs**: the metric counts questions whose
outcome ever differed, so pooling six runs of the same prompt gives 12.8% — higher
than either triple by construction, not because the system got less stable.
"Cross-run variance > 10%" therefore has no fixed value until the run count is
fixed, and the ADR never fixed it. At three runs it is a coin flip; at six it
fires; at two it would almost never fire.

> **So the 10.6% that fired this threshold was a sampling artifact, and the
> reversal condition as written — "a second full×3 clearly above 10%" — cannot
> settle anything either.** The replication came back at 4.3%. If the rule is
> read literally, threshold 3 has now both fired and not fired on the same prompt.

**What should replace it,** for whoever revisits this: state the metric as a
per-question stability rate at a fixed run count (*"no more than N of 47 questions
change outcome across exactly 3 runs"*), or measure the thing the threshold was
actually worried about — whether a *specific* answer a reader would see changes
between showings. The current definition measures the sampling budget as much as
the model.

### Three things the replication found that one triple could not

**q017 was never a consistent failure.** Across six runs of the same prompt it is
`wrong, wrong, wrong, correct, correct, correct`. The runs that failed wrote
`HAVING count(*) FILTER (late) > 0`; the runs that passed wrote
`HAVING avg(actual) > avg(contracted)`. **The model oscillates between two
defensible readings of a question that does not say which it wants** — which is
what an under-determined question looks like from the outside, and it settles the
attribution argued above from the text alone. ADR-0001 called q017 one of two
"consistent failures … specific and addressable". It was neither consistent nor
the model's.

**The 100% on view-covered questions was also an artifact.** q032 — a
view-covered question, previously 33/33 — returns `wrong_rows` in run 4 and
correct in the other five. Six runs give 65/66 (98.5%). The resolution cited
"100% on view-covered" as support; the real number is "one failure in 66, found
only by running it twice as many times".

**q026 is the one genuinely stable failure**, and it is stable in an unusual way:
`execution_error, wrong_rows, execution_error, wrong_rows, execution_error,
wrong_rows` — perfectly alternating across six runs, never once correct. Its
timeouts are real. Its `wrong_rows` disagree with a reference that
`evals/FIX-LIST-v2.md` item 16 already flagged for hardcoding a festive window
that q024 and q025 read from the `festivals` table, so even here the instrument is
not clean.

### The pooled accuracy figure, and why it is weaker than it looks

182/198 = **91.9%, CI 87.3–95.0%**, the first interval in this project's history to
**exclude 85%** — which by this ADR's own rule means "the measurement decides", and
it decides above the line. The ADR predicted that resolving this would need
"several hundred questions, which is a benchmark, not this project", and missed
that repeated runs tighten the interval far more cheaply.

**But the interval is optimistically narrow and should not be quoted as if it
were not.** Wilson assumes independent Bernoulli trials. Six runs of the same 47
questions are clustered: run 4 of q032 tells you almost nothing new about q032's
difficulty, and nothing at all about the other 46. Pooling inflates *n* without
adding proportional information, so the true interval is wider than 87.3–95.0%.
The defensible claim is the modest one: **no measurement taken has put accuracy
below 85%, and the point estimate has landed between 88.9% and 93.9% on every
sample.**

## Two decisions taken 2026-08-09, and what reverses each

Both were left open for a second pair of eyes and then explicitly delegated. Both
were resolved by measuring rather than by ruling.

### 1. Threshold 1 does not fire, and the test was controlled

Rather than withdraw the failing questions and count what was left — which is
score management however good the reasons — each was made to determine its own
answer and then re-measured. Nine calls, ~$0.21.

| | change made | before | after |
|---|---|---|---|
| **q017** | question only; reference untouched. It now says *average* delivery time against *average* contracted lead time, which the old wording left open | `wrong_rows ×3` | **`correct ×3`** |
| **q026** | question names the four ramps and the baseline; reference reads the window from the `festivals` table instead of hardcoding it (`FIX-LIST-v2` item 16) | `exec_error, wrong_rows, exec_error` | **`exec_error ×3`** |
| **q049** | withdrawn; **q050** replaces it as set membership against a stated threshold | `wrong_rows ×3` | **`correct ×3`** (q050) |

**q017 settles the argument.** The reference was not changed — only the question
was — and the same model on the same prompt went from three failures to three
passes. It was the ambiguity, not the capability. ADR-0001 called this one of two
"consistent failures … specific and addressable"; it was neither consistent nor
the model's, and the six-run data had already shown it choosing each reading three
times.

**q026 is the genuine failure and it is not a silent one.** With the window and
baseline determined, it times out three times out of three. An execution error is
visible, recoverable, and explicitly the failure mode this project prefers —
`sql_generate.md` asks for wrong-and-obvious over wrong-and-plausible. **It is not
a silent-wrong and threshold 1 does not count it.**

> **So: zero silent-wrongs on the current set, and threshold 1 does not fire.**
> **What reverses this:** any silent-wrong in the clean triple of the current set,
> or a later run. This disposition rests on three questions having been rewritten
> in response to their own failures, which is the correct fix for an
> under-determined question and is also the shape of instrument tuning — so it is
> recorded here rather than folded quietly into a number.

> ### RETRACTED THE SAME DAY. The clean triple fired the reversal condition above.
>
> **Threshold 1 fires: five distinct questions produced a silent-wrong** — q011,
> q026, q034, q043, q047 — in a fresh triple of the current set at `--run-offset 3`
> (147 calls, 0 cache hits, ~$3.32).
>
> **The "zero silent-wrongs" reading was a selection effect, and the size of it is
> the lesson.** Only the three questions that had failed were re-measured, so
> failures got a second draw and successes did not. Re-scoring on that basis gave
> **97.1% and 0.0% variance**. The clean triple over the identical set gave
> **91.4% and 12.2%** — the same point estimate as the first triple, 5.7 points
> below the flattering one. The questions that came back clean were the ones that
> had been re-rolled; the ones that had not were where the instability was.
>
> **q017's result survives, and it is the one that mattered.** It is correct in all
> six runs of the current set. Making the question determinate fixed it, which is
> the finding — ADR-0001's "consistent model failure" was the wording.
>
> **What actually fires threshold 1 is instability, not incapacity.** Every one of
> the five is `correct` in at least one run of the same triple, and four of them
> were correct three times out of three in the previous one. This is the same
> texture the six-run study of the old prompt showed: **roughly five or six of
> ~49 questions flip on any given draw**, and which five is not stable either.
>
> **A conclusion drawn from re-measuring only what failed lasted about an hour.**
> That it was written with an explicit reversal condition is the only reason the
> retraction is this cheap — and it is the argument for writing them that way.

### 2. Threshold 3 is retired as a trigger, and kept as a diagnostic

**It cannot resolve its own line at this sample size, and that is now measured
rather than argued.** Two triples of the identical prompt over the identical
questions returned 10.6% and 4.3%, landing on opposite sides of the 10% line. The
metric is also monotone in the run count, so the same system reads 12.8% over six
runs. This ADR already made exactly this argument about accuracy — *"at n≈40 a
rate is a worse instrument than it looks"*, bounds tight enough to resolve five
points "need several hundred questions, which is a benchmark, not this project" —
and the argument applies with more force to a rate computed over 47 questions and
three draws.

**Decision: cross-run variance is reported with its run count and never triggers
the catalog on its own.**

**What replaces it, for the concern it was actually about.** The stated harm was
*"non-determinism is fatal for a repeated demo"*, and demo mode answers from a
fixed file, so that harm is gone by construction. The harm that remains is on the
live path and is narrower: **an answer that is wrong in some runs and right in
others.** That is strictly worse than a stable wrong answer, because it cannot be
caught by reviewing the query once. **Threshold 1 already covers it** — a
silent-wrong counts if it appears in *at least one* run — so the concern is
already triggered by the threshold that measures harm rather than by a rate that
measures the sampling budget.

**What reverses this:** a variance measure that is stable across independent
triples of the same prompt. If two triples ever agree closely, the metric is
resolvable after all and can carry a line again.

> **Strengthened the same day.** Two triples of the *current* prompt over the
> *current* 49 questions returned **0.0% and 12.2%** — a wider disagreement than
> the 10.6%/4.3% pair that prompted the retirement, and now across four
> independent triples the metric has read 0.0, 2.0, 4.3, 10.6 and 12.2 percent on
> a system that did not change. (The 0.0% is itself the selection-effect
> re-score, which is part of the point: the metric is as sensitive to how you
> sample as to what you are sampling.)

### One thing the timeouts are not: my fault

q026 times out in five of six runs and q050 in two of three, and both were
measured while a test suite and two dev servers were using the same Postgres.
That is a real confound and it was checked rather than assumed: **the exact SQL
from both failing q050 runs was re-executed against an idle database and both hit
the 5s statement timeout at 5.005s.** The run that succeeded used a different
idiom — a `DISTINCT` set of festive dates joined once — where the two that failed
tested festival membership with a correlated `EXISTS` per row over 419,513 rows.

So the finding is about the idiom and its grain: **`EXISTS` per row survives at
chain grain (1.5s) and dies at category grain**, and the model picks between the
two formulations from run to run. That is the only stable model-side failure in
the set, and it is a visible one.

**Build the catalog if any threshold fires:**

1. **Any silent-wrong result — investigated individually, regardless of rate.**
   Executes cleanly, returns plausible wrong numbers. Overrides the others,
   because it is undetectable live. Measure by comparing result sets, not by
   whether the query ran. **One silent-wrong is a signal to diagnose. Two or
   more distinct questions producing silent-wrong results fires the catalog
   decision.**
2. **Execution accuracy below 85%, judged against a confidence interval.**
   Report as `83.3% (25/30, 95% CI 66–93%)`. If the interval **excludes** 85%,
   the measurement decides. If it **straddles** 85%, the result is
   inconclusive — and the response is more questions *targeted at the observed
   failure modes*, not more questions in general.
3. ~~**Cross-run variance > 10%**~~ — **RETIRED 2026-08-09 as a trigger** (reported, never fires on its own): two triples of the same prompt returned 10.6% and 4.3%, and the metric rises with the run count by construction. See "Two decisions taken 2026-08-09".
4. **Median attempts-to-correct > 1.3** — a retry loop is a quota problem stacked
   on an accuracy problem.

### Why 1 and 2 are stated that way

Both were originally rates. At this sample size a rate is a worse instrument
than it looks, and stating them as rates would have produced decisions the data
cannot support.

**Threshold 1 was already a count wearing a percentage.** At n≈40, one
silent-wrong is 2.5% and two is 5%. Nothing lands *at* 5%, so "greater than 5%"
resolves to "two or more" and always did. Saying so directly is both stricter
and more honest, and it forces every silent-wrong to be diagnosed individually
instead of averaged into a rate where one failure hides among forty passes.
A single confidently-wrong answer to an agent that will act on it is not a
rounding error.

**Threshold 2 needs an interval because the point estimate is not the finding.**
Observed 25/30 is 83.3%, which reads as "below 85%, build the catalog" — but the
Wilson 95% interval is 66–93%, which straddles 85% and supports no decision at
all. Growing the set does not rescue this: 42/50 is 84.0% with an interval of
71–92%, still straddling. Bounds tight enough to resolve a five-point difference
need several hundred questions, which is a benchmark, not this project.

So the honest posture is: **measure, publish n and the interval every time, and
act only when the interval clears the line.** When it does not, the useful next
step is targeted questions probing whatever actually failed — which narrows the
question, rather than more questions in general, which mostly does not.

`api/scripts/wilson.py` computes the interval, so the published figure is
derived rather than asserted, and a test pins the 25/30 case.

### A failing question is a diagnostic, not a thing to patch

The few-shot pairs in `sql_generate.md` are deliberately **not** drawn from the
eval set, and one omission is worth recording because it will look like an
oversight later.

There is no few-shot pair demonstrating how to split a tax figure at the
22 September 2025 GST reform. One was drafted and dropped. Whether
`business_context.md` alone is enough to teach that split **is the measurement
this ADR exists to take**, and q018 is the instrument that takes it. A few-shot
pair showing the answer would destroy the instrument while appearing to improve
the score.

**So: if q018 fails, the fix is improving `business_context.md` — not adding a
few-shot pair.** The same holds for any question that fails. Converting a
diagnostic into a patch is the failure mode this whole approach is meant to
avoid: it raises the number and teaches you nothing, and the next unseen
question fails the same way with no warning left in the instrument.

**This applies to the Phase 2 extraction numbers too.** Header-field accuracy,
line-item F1, hallucination and miss rates all get n and an interval, every
time they are reported. A hallucination rate of "2%" over 50 documents is one
document, and should be written so a reader can see that.

### The measurement has to survive its own convenience layer

Phase 0 shipped a small set of views — `v_stock_status`,
`v_product_velocity_30d`, `v_supplier_terms_current`, `v_supplier_price_current`
— that encode the metric definitions a question would otherwise have to
reconstruct. That is legitimate schema design and it is the same bet this ADR
already makes: context does the work. But it moves the thresholds.

A question that a view answers is close to `SELECT * FROM view WHERE ... ORDER
BY ...`. If enough of the eval set looks like that, threshold 2 measures the
view rather than the model, and an inflated number keeps generated SQL alive
when the measurement should have killed it.

**So every question in `evals/sql/questions.jsonl` carries a `view_covered`
boolean, and the results block reports execution accuracy three ways: overall,
view-covered, and not-view-covered.** The threshold is evaluated against the
**not-view-covered** number, because that is the one describing what the model
can actually do. One extra field in the JSONL, and it is the difference between
a measurement and a flattering one.

**Pre-committed hybrid, regardless of results:** hand-write query templates for
the 10–15 questions the demo actually asks. Generated SQL handles the tail. The
demo path is deterministic even if general accuracy is excellent. This is not
hedging — it is declining to gamble on live inference for the thing being judged.

## Alternative rejected

A full curated query catalog from the start.

## Why

The evidence for it was drawn from a much harder problem than this one, and its
strongest sources had a commercial stake in the conclusion. A catalog also
carries a maintenance tax — every new question is a code change — which
reproduces exactly the rigidity this project set out to fix. And if the thesis is
"natural language over business data", a fixed catalog is a weaker demonstration
of it.

## What would flip it

Any of the four thresholds firing in Phase 1 measurement. Nothing else — not
argument, not a new benchmark. When the measurement lands, update this ADR rather
than writing a new one; a reader should find the question and its resolution in
one place.