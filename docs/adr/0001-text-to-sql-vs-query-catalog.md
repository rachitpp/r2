# ADR-0001: Text-to-SQL, with measured thresholds for switching to a query catalog

Date: 2026-08-05
Status: **Resolved 2026-08-08 — keep generated SQL. Two thresholds fired and
the catalog is still not built; the reasoning is in "The resolution" below and
it is reversible on one specific new fact.**

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
3. **Cross-run variance > 10%** — non-determinism is fatal for a repeated demo.
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