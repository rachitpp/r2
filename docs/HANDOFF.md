# HANDOFF — canonical state

**This file is the state document pasted into new sessions. It lives in the repo
on purpose.**

The previous handoff was maintained outside version control, and by 2026-08-07
it was falsified in five places while still reading as authoritative — the
document with the highest blast radius in the project was the only one with no
review, no history, and no agent able to correct it. A session receiving both it
and `PROGRESS.md` would have believed the wrong one, because the pasted copy
arrives first. That is the project's recurring defect class one level up, and
moving this file into the repo is the fix.

Read alongside: `docs/PROGRESS.md` (session state), `evals/README.md` (how the
instrument works), `evals/DIAGNOSIS-2026-08-07.md` (why it currently doesn't),
`evals/FIX-LIST-v2.md` (the decision artifact).

---

## Where the project is

**Phase 1 — Structured Q&A, at the end of enumeration.** Phase 0 is complete.

The 47×1 SQL eval has been measured, fully diagnosed, and **all 30 passes
audited**.

> ### THERE IS NO HEADLINE NUMBER. Do not quote one.
>
> The raw figure from the 47×1 run is **retired** and deliberately not repeated
> here. It is wrong in **both directions and by unknown amounts**: at least
> **11 instrument defects deflate it**, while **q039 and q008 inflate it** —
> they pass only because the model happened to match an arbitrary `sku`
> tiebreak. Neither direction dominates and neither magnitude is known.
>
> That is the asymmetric-matcher risk the eval design warned about, actually
> realised. **No accuracy number exists for this project until the v2
> re-measure.** It must not appear in a commit message, the README, or any
> portfolio text before then.

**No fixes have been applied.** Enumeration is complete; the batch waits for the
instrument v2 sitting.

---

## Five corrections to anything you were told earlier

If you are working from an older handoff, these five claims in it are wrong.

### 1. The seventh axis is row identity, not "free-text labels"

It was first written up as *"free-text labels the query invents"*, illustrated
with q019 returning `'Before Sep 22, 2025'` against the reference's `'before'`
with **identical numbers**.

**That illustration is false.** q019 returned **8.30 / 7.08**, not the
reference's 8.23 / 6.73 — and 8.23 / 6.73 are the constants
`business_context.md` publishes as the true effective rates. The expected values
had been transcribed into the observed slot and a hand-verification asserted
over them. Re-checked, the axis was wrong in **3 of its 4 questions**.

The real axis: **the question does not determine which column identifies a row.**
`stores.code` (`ST-01`) and `stores.name` (`Kothrud`) both name it — two real
data columns, so q042 was never a "label" case at all. Two further axes exist:

| axis | what it is |
|---|---|
| **7 — row identity** | Which column names a row is under-determined |
| **8 — ratio magnitude** | "Share" does not fix `0.05` vs `5.0` |
| **9 — disambiguation was unscoreable** | Scored on stated reasoning that `sql_generate.md` line 6 forbids the model from writing |

### 2. q043 is a model failure; its reference was never wrong

`evals/README.md` listed it among four reference-author errors. Its
`reference_sql` was **never edited**. Rotation 4 fixed its *question*, which had
not named the period the reference already filtered on.

It now fails for an unrelated reason and the failure is **the model's**: it used
`subtotal` where `business_context.md` says plainly to use `total` for *what a
customer paid*. Second unambiguous model failure, after q026.

### 3. The stopping rule was falsified and is replaced

The old rule — *every question must be model-tested and the instrument corrected
against it* — **was satisfied**, and **8 of the 14 failing references had never
been revised**. Agreement was being consumed as a positive result when it is a
null one.

> **New rule: a reference is verified when every predicate *and its grain*
> traces to specific words in the question, every number the question names
> appears in it, no `LIMIT` cut falls inside a tie, and question, reference,
> `intent` and `traps` agree. Model agreement does not discharge this.**

**It has been run once, prospectively, and it worked.** Across all 47 references
it found **five whose `LIMIT` falls inside a tie** — the tiebreak deciding
membership rather than order — four of them new, in references that had already
survived diagnosis and a pass audit. It overturned a "sound" verdict (q039) and
gave q011 and q042 a second defect each. **q042 has 5 of its 10 slots contested
among 13 tied products.** Three clauses of the rule above were added *because*
the run exposed them.

Its limits are stated in `evals/README.md` and matter — see the `is_active`
blind spot below for what it still cannot see.

### 4. q004 is `context`, not `ambiguous`

Re-bucketed against the favourable direction. `ambiguous` should mean two
readings *no context document could settle*; this one settles in a sentence
(does an explicit cover threshold replace the reorder-point default or add to
it?). It therefore means **`business_context.md` is incomplete**.

**Consequence that drives sequencing:** its fix edits `business_context.md`,
which changes the prompt fingerprint and **voids all 47 cached responses**.

### 5. Instrument v2 is a pending decision, not a settled one

See `evals/FIX-LIST-v2.md`. Recommendation recorded, **to be decided in a
sitting separate from the evidence that prompted it.**

---

## The `is_active` blind spot — GATED, do not fix

**All 600 products have `is_active = true`.** Generated SQL frequently adds
`AND p.is_active = true` — an unstated predicate the question never asks for. It
**cannot change any answer under the current seed**, so the instrument is
structurally unable to detect it, and it passes every check including the new
predicate-trace rule.

**It becomes live the moment the seed contains an inactive product**, and it
would then silently move several answers at once.

It is **not being fixed**, deliberately. The seed is `random.Random(42)` with
derived substreams, so changing it invalidates every expected result set in the
eval. The cost of fixing the blind spot exceeds the cost of the blind spot,
under this seed.

> **GATE: if the seed generator is ever changed, re-check every reference and
> every cached generated query for `is_active`, before regenerating
> expectations.** This is the flag; it is deliberate, and it is the kind of
> thing a later phase trips over.

---

## Why the live model path waits for the v2 sitting

**The primary reason is not quota.** It is that **q004's fix edits
`business_context.md`, which changes the prompt, which changes what the live
path produces.** Building and testing a generation path against a prompt already
known to be about to change means validating the wrong artifact — the tests
would pass against something that no longer exists the moment the batch lands.

Quota is the *second* argument: the live path competes with the ~47-call
re-measure for 20 requests/day.

The ordering matters because it decides whether the sequencing still holds if
quota stops being scarce. **It does.** A credit balance turning up would remove
the second argument and leave the first untouched — so the live path waits for
the v2 sitting either way, and specifically for the q004 fix to land, not merely
for calls to become cheap.

---

## Budget vs actual, per phase — check this before starting work

**Phase 1 was budgeted ~32h. The eval diagnosis alone ran to a large multiple of
that, and nothing registered it while it happened.**

`PLAN.md` holds each phase's definition of done. `PROGRESS.md` tracks what
landed. **No artifact compared them**, so effort could accumulate against a
measurement apparatus while the phase's actual deliverable — *a question asked
in the web app, answered beside the query that produced it* — stayed at zero.

That is **the recurring defect class in the plan** rather than in the
instrument: a check that is not running (deliverable against budget) wearing the
label of one that is (commits against progress notes).

| Phase 1 | budgeted | actual | state |
|---|---|---|---|
| eval harness + diagnosis | part of ~32h | large multiple | enumeration closed |
| API query endpoint | part of ~32h | **demo half done** | `POST /query` serves answer + SQL with no key and no quota; live model path returns 501 |
| `web/` — Next.js, tokens, typed client, SSE | part of ~32h | **does not exist** | blocked on the design plan being agreed — proposal written at `docs/DESIGN-TOKENS.md` |

> **Rule: check deliverable-against-budget at the point where it can still
> change what you do**, not at phase close. The audit was the right work and the
> handoff nominated it — the defect is that nothing was watching the ratio while
> it ran.

---

## Cross-run variance is DEFERRED, not dropped

`full×3` is the third stage of the staged-run rule (5×1 → full×1 → full×3) and
**it has not been run.** Every diagnosis in this session rests on **one sample
per question**.

That matters more than a README line. ADR-0006 scopes determinism to the **parse
layer precisely because the model layer has none**, and Vertex serves this model
from `location=global` with no determinism guarantee. **If run-to-run variance is
large, the 47×1 figure means less than this audit has been treating it as
meaning.**

**Dropping `full×3` would be the instrument loosening in a further direction —
by omission rather than by fix**, which is harder to see and therefore worse.

So it is deferred to **Phase 1 close**, with a cheap substitute first:

> **Variance spot-check: 5–8 questions × 3 runs, ~20 calls, one day of quota.**
> Pick the ones the diagnosis leans on hardest — q018's reform split, q009's
> returns trap, and the tie cases once fixed. If variance is small, the
> single-run numbers can be trusted until the full×3 and nothing rests on an
> unmeasured assumption. If it is large, that changes how the whole audit reads
> — learned cheaply, and before spending a week of quota.

---

## What the instrument is and how it fails

The eval measures execution accuracy over 47 natural-language questions against
a Postgres retail schema, scored by deterministic result-set comparison — no
LLM-as-judge. Reported three ways: overall, view-covered, not-view-covered, with
thresholds read off the **not-view-covered** number.

**Its dominant failure mode is not the model.** Nine axes of instrument defect
have been found, and the direction never once scatters: **every reference error
has favoured the reference and run against the model.** The cause is structural
— the author knows what they meant, so the reference looks obviously right in
retrospect. Inverted authoring is the preventive fix; the predicate trace is the
verification one.

**The recurring defect class, eight instances:** *a check that is not running,
wearing the label of a check that is.* It has appeared in a column name, an
empty expectation, the matcher, the pre-commit hook, a passing eval row, a
**process rule** (the old stopping rule — worst, because it licensed the others
to stop looking), the conjunct splitter, and finally **the probes built to hunt
the class itself**.

### Instance eight changes a standing claim — read this before repeating it

This project has said throughout that the class is only ever caught **by use**:
by rotating questions, by a model disagreeing — *never* by a test failing. See
`evals/README.md` → *What four staged runs cost*, and `CONVENTIONS.md`.

**That is no longer true, and instance eight is the counter-example.** Five
probes failed silently, all from one cause — regexes guessing at SQL structure
instead of parsing it — and **two of the five were caught by a failing
assertion**, not by inspection and not by a model disagreeing. The probe refused
to report a result because it had missed a defect it was *required* to find.

The mechanism is cheap and worth copying: **give every probe a known-positive it
must find, and make missing it a hard failure.** A probe with no known-positive
cannot tell "found nothing" from "looked at nothing" — and a checker is always
easier to write than to validate, which is exactly why the validation is what
gets skipped.

So the claim should now be stated as: *inspection alone does not catch this
class, and use catches it late — but an assertion with a known-positive catches
it at the moment it is written.*

---

## Every singleton, checked as a class

The standing rule is that **any defect found once is a candidate class until
someone checks mechanically.** All of them have now been checked. The result is
the argument for doing it:

| singleton found | checked? | became |
|---|---|---|
| q012 — `LIMIT` cut inside a tie | yes | **5** (q008, q011, q012, q039, q042) |
| q031/q047 — ranks on a rounded column | yes | **3** (q033 new, latent) |
| q019 — narrows an unstated period | yes | **2** (q019, q026) |
| q024/q042 — row identity | yes | **2 manifest of 12** — and it *reframed*: the reference set is inconsistent, not the questions under-determined |
| q047 — ratio magnitude | yes | **1** — the references are consistent; the model diverged once |
| q035 — `GROUP BY` grain conflation | yes | **1** |
| q005 — stale `intent` | yes | **1** |
| q024 — stale `traps` tag | yes | **0 — retracted**, the convention is universal |
| `is_active` — model-side unstated predicate | **impossible in kind** | a reference-side rule cannot see a predicate the model adds |

**The prior was uninformative in both directions.** One singleton became five;
two stayed singletons; one went to zero and had to be retracted. Nothing about
how a defect *looked* when first found predicted what the check would return —
which is why the check is mechanical and not a judgement call.

---

## Hard constraints that do not relax

- **No model calls in CI.** Anything needing a key is a local `make` target.
- **Free tier is 20 requests/day/model**, measured. `PLAN`, `CLASSIFY` and
  `EXTRACT` route through Vertex (ADR-0009, ADR-0010). Vertex serves from
  `location=global` only.
- **Every eval runs against `full`**, never `small` — they are independent
  datasets, not subset and superset.
- **Re-scoring is free; re-running is not.** Every response is cached under
  prompt fingerprint `de60dd5e3dde7787`. Reference fixes re-score at zero cost.
  **Any edit to `business_context.md` or the prompt voids all 47** — roughly
  $0.99 and ~2.3 days at 20 RPD.
- **`AS_OF_DATE = 2026-06-30`, never wall-clock.** `current_date` is forbidden
  in generated SQL.
- **Credentials never enter the repo.** `make hooks` installs a pre-commit
  content scan; history has been verified clean.
