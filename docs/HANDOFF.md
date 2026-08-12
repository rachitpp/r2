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

**Phase 2 — Corpus ingestion. IN PROGRESS.** Phase 0 and Phase 1 are complete;
Phase 1 closed 2026-08-09. Closing it did not claim the eval is clean: it claimed
the deliverable works, the measurement has been taken six times, and the
remainder is debt that does not block anything. The debt is in `PROGRESS.md`.

**The corpus is no longer the blocker — it exists.** 40 synthetic documents
generated from the seeded database, and all 40 parsed with Docling into
`corpus/parsed/`.

**Extraction is built and has never been run.** Prompt, schemas, validator,
runner and 31 tests, all exercised against a stub — no key, no network, no model
call. `corpus/extracted/` does not exist, so **building the pipeline moved no
done-condition.** Code is not measurement. Three things gate the first run and all
three are yours: a GCP budget alert, data residency for `location=global`, and the
canonical Vertex terms. See `PROGRESS.md` → *Next session should*.

**Phase 2 is at 4 of 7.** Done-condition 4 was closed on 2026-08-11: the corpus
had no coverage gaps at all while `corpus/README.md` asserted it did, and the seed
now lapses SUP-06 for 48 days and SUP-11 for 78. Two expected result sets moved
(q017, q048) and exactly 2 of 40 PDFs changed.

> **THE PUBLISHED ACCURACY NUMBERS ARE STALE.** They were measured against seed
> `206fb7a8e55164f9`; the seed is now `e1ca4fb60f9e710e`. Restoring them is **not**
> a free re-score — `evals/.cache/` is gitignored and exists only on the machine
> that made it, so it means re-running: 147 calls, ~$3.30, and a Vertex service
> account. Marked stale in `PROGRESS.md` per `CONVENTIONS.md`. The error is
> probably small and bounded — two questions, one value each — but "probably" is
> not a measurement and the README quotes these as if they were.

**The database is on Neon (PostgreSQL 18.4), and its free tier cannot hold this
project's design at `full`:** 512 MB cap, 263 MB database, so the
template-plus-clone that `make reset` and ADR-0005's test isolation both need does
not fit. `make db` fails at its last step and the 33 DB-marked tests cannot run at
`full` there. Migrations themselves applied cleanly on PG18, which had been an
assumption since Phase 0.

**Amendments vs. supersessions is decided: clause-level provenance.** Extraction
records what a document says, never what was in force. No migration was written —
`supplier_term_clauses` would void 147 cached eval responses for ~$3.30 and no
Phase 2 done-condition needs a table. It belongs in Phase 3.

> **This file said "Phase 2 is blocked on the corpus, which does not exist yet"
> for two commits after the corpus was generated and parsed.** Both landed
> without touching it or `PROGRESS.md`, so the two state documents disagreed with
> the repository they describe — and this one arrives first in a new session, by
> design, which is the specific failure mode moving it into the repo was meant to
> prevent. Being version-controlled made it *correctable*; it did not make it
> correct. **The rule that would have caught it is already written in
> `CONVENTIONS.md`: update `PROGRESS.md` as the last action of every session.**

The eval has been diagnosed, fixed, and measured **six times** — three triples of
the current prompt and three of the previous one.
**`web/` now exists and demo beat 1 runs end to end** — a question asked in the
browser returns the answer beside the SQL that produced it, with no key and no
quota. `make serve` and `make web`. **The live model path is built beside it**
(`DEMO_MODE=false`, `make serve-live`) and has been proven against the real model:
three Vertex calls, ~$0.06, an answer and a refusal and a clerk-scoped query.

> ### PHASE 1 IS MEASURED SIX TIMES, AND THE SAMPLES DISAGREE
>
> | sample | prompt | questions × runs | not-view-covered | variance |
> |---|---|---|---|---|
> | first triple (0–2) | `415953…` | 47 × 3 | 88.9% (88/99, CI 81.2–93.7) | **10.6%** |
> | **replication (3–5)** | `415953…` | 47 × 3 | **93.9% (93/99, CI 87.4–97.2)** | **4.3%** |
> | _pooled, not a triple (0–5)_ | `415953…` | 47 × 6 | 91.9% (182/198, CI 87.3–95.0) | _12.8%_ |
> | triple, pre-fixes (0–2) | `f3b7a9…` | 49 × 3 | 91.4% (96/105, CI 84.5–95.4) | 2.0% |
> | re-score after fixes (0–2) | `f3b7a9…` | 49 × 3 | 97.1% — **biased, do not quote** | 0.0% |
> | **CURRENT: clean triple (3–5)** | `f3b7a9…` | 49 × 3 | **91.4% (96/105, CI 85–95)** | **12.2%** |
>
> **Threshold 3's firing was a sampling artifact.** Two triples of the identical
> prompt over the identical questions returned 10.6% and 4.3%, with the 10% line
> between them. The metric also counts questions whose outcome *ever* differed, so
> it rises with the run count by construction — 12.8% pooled over six runs. It has
> no fixed value until the run count is fixed, and the ADR never fixed it. **Do not
> quote "two thresholds fired".**
>
> **Threshold 1 FIRES: five distinct silent-wrongs** — q011, q026, q034, q043,
> q047 — in the clean triple. **None of them is stable**: every one is correct in at
> least one of the same three runs, and four were correct 3/3 in the triple before.
> Which five questions fail is not stable between triples either.
>
> **It was ruled "does not fire" earlier the same day and that lasted an hour.** The
> ruling rested on re-measuring only the three questions that had just been fixed,
> which read 97.1% with zero silent-wrongs; the clean triple over the identical set
> read 91.4% with five. **Never re-measure only what failed** — see ADR-0001.
>
> **Threshold 2 has never fired and has never been resolvable on one triple.** The
> pooled six-run interval (87.3–95.0%) is the first to exclude 85%, but it is
> optimistically narrow — six runs of the same 47 questions are clustered, so Wilson
> understates it. The defensible claim: no sample has put accuracy below 85%, and
> the point estimate has landed between 88.9% and 93.9% every time.
>
> **Threshold 4 is still unmeasured.** No retry loop exists.
>
> **q036 is fixed and it holds: refusal 6/6** across both triples of the current
> prompt, up from 2/3. The way it could have been worse than the defect was
> over-refusal, and there is **zero `refused_wrongly` anywhere in the clean triple**
> — q047's one failure is `wrong_rows`, not a refusal. The fix was a
> `business_context.md` section, not a few-shot pair, per the ADR's own rule.
>
> **q017 is fixed too, and by the cleanest test available: the question changed and
> the reference did not.** Correct 6/6 on the current prompt, from `wrong ×3`.
>
> ---
>
> ### How much of the original figure was the instrument
>
> Holding
> the model's answers completely fixed and correcting only the instrument moved
> not-view-covered from **23/33 to 29/33**. That is the honest attribution: six
> of the ten original failures were never the model's.
>
> **And the direction has still never once reversed.** Eleven axes now. The two
> found on 2026-08-08 were a false schema comment about `expected_on` that licensed
> q017's failure, and a question of our own that scored a correct answer wrong three
> times.

**The whole instrument batch is applied**, including the forks: tie-completion
lives in `scoring.py`, q042 was made consistent with its six siblings rather
than loosening the matcher, and q004's context gap is closed. `evals/FIX-LIST-v2.md`
is now a record of what was done rather than a decision page.

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

It then failed for an unrelated reason and the failure was **the model's**: it used
`subtotal` where `business_context.md` says plainly to use `total` for *what a
customer paid*.

**That is no longer the present state, and the correction is instructive.** Across
six runs of the previous prompt q043 is `correct` once; across six of the current
one it is correct four times — `correct 3/3` in one triple and
`correct, wrong_rows, wrong_rows` in the next. So "second unambiguous model
failure" described one triple, not the system — the same mistake threshold 3 made.
**q043 is unstable, not fixed and not broken**, and nothing in the causation fix
has any obvious bearing on `subtotal` versus `total`.

### 3. The stopping rule was falsified and is replaced


The old rule — *every question must be model-tested and the instrument corrected
against it* — **was satisfied**, and **8 of the 14 failing references had never
been revised**. Agreement was being consumed as a positive result when it is a
null one.

> **New rule: a reference is verified when every predicate *and its grain*
> traces to specific words in the question, every number the question names
> appears in it, **the question determines the shape of its answer — how many
> rows and what identifies one**, no `LIMIT` cut falls inside a tie, and
> question, reference, `intent` and `traps` agree. Model agreement does not
> discharge this.**

**The shape clause was added 2026-08-08, by breaking it.** q049 passed every other
clause and still failed three times while returning values numerically identical to
its own reference — one row of two columns against two labelled rows, 1dp against
2dp. Declaring `result_shape` and `answer_columns` does not discharge it: **the
model never sees those fields.** Checked as a class, q009 is the one latent case
left in the set; q024 shows the fix, which is to let order carry identity and keep
the invented label out of `answer_columns`. Full write-up in `evals/README.md`.

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
which changes the prompt fingerprint and **voids every cached response**. (Done on 2026-08-08; it cost 147 calls to re-measure.)

### 5. Instrument v2 is applied, measured, and ADR-0001 is resolved

The batch landed, `full×3` ran, and the ADR now says **keep generated SQL**. The
reasoning is in the ADR, it names what would reverse it, and it was written by the
agent that ran the measurement rather than in a separate sitting.

**This paragraph read "two thresholds fired and the catalog was still not built"
until 2026-08-12, 141 lines below the box in this same file that says *do not
quote "two thresholds fired"*.** Threshold 3's firing at 10.6% was a sampling
artifact — a strict replication of the same prompt and questions returned 4.3%,
and the metric has no fixed value until the run count is fixed. **Threshold 1 is
the one that fires.** The ADR's conclusion survives; two of its three stated
reasons do not. A file can carry its own correction and still be quoted from the
wrong half, which is why the correction now sits in both places.

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

## The second blind spot: `business_date` vs `sold_at` — GATED, and impossible in kind

Found 2026-08-08 by checking the schema comments mechanically, after one of them
turned out to be false about the data (`expected_on`). Any defect found once is a
candidate class until someone checks, so all 52 `COMMENT ON` statements were
scanned for claims that assert a data property, and the 18 that do were tested.

**Five held.** `sales.subtotal = sum(sale_lines.line_total)` (0 violations in
217,513 sales), `inventory.on_hand = movements − sale_lines` (0 in 1,800),
`v_supplier_terms_current` = the rows with no end date (exact), supplier terms
never overlap (0), and staff display names are role-and-ordinal — `Owner`,
`Manager 01`, `Clerk 01-01`, none person-like, as ADR-0002 requires.

**One is false.** `sales.business_date` is documented as "not always equal to the
UTC date of `sold_at`", and `business_context.md` line 61 goes further: `sold_at::date`
"will disagree with `business_date` for late-evening transactions" and aggregating
on it is "quietly a little wrong". **They never disagree — 0 of 217,513.** And this
is structural, not seed luck: IST is UTC+5:30 and the stores trade 08:00–21:59
local, which is 02:30–16:29 UTC, so the calendar date cannot differ. No reseeding
produces a counter-example without trading past midnight or moving the chain to a
timezone behind UTC.

**Consequence: the `business-date-vs-sold-at` trap tag cannot fail.** A query that
aggregates on `sold_at::date` returns identical numbers here, so the instrument is
structurally unable to detect the mistake it is tagged as testing — the same shape
as `is_active` above, and instance eleven of the recurring class.

**Deliberately not fixed, for one reason: correcting either document changes the
prompt and voids the 147 responses measured today.** The false claim steers the
model toward `business_date`, which is the right column regardless, so it costs no
accuracy — it costs honesty, and one eval tag.

> **GATE: at the next prompt unfreeze, correct both documents in the same batch.**
> Keep the instruction, replace the justification: the two coincide in *this*
> dataset because of the trading hours and the timezone, which makes the mistake
> invisible here rather than harmless, and it would surface immediately for a
> store trading past midnight or in a timezone behind UTC. Then either retire the
> `business-date-vs-sold-at` tag or say in `evals/README.md` that it is
> unmeasurable, so it stops reading as coverage.

---

## The live model path — built, opt-in, and never yet called a real model

It waited on q004's fix editing `business_context.md`, on the grounds that
building a generation path against a prompt known to be about to change means
validating the wrong artifact. **That fix landed** (prompt re-frozen
`415953964db74b80`), so the path was built: `api/src/pos_copilot/live.py`,
`DEMO_MODE=false`, `make serve-live`.

**Three things about it that a later session needs.**

**1. It does not replace the canned demo path, and must not.** ADR-0001's
resolution rests on demo mode answering from a fixed file with zero model calls
— that is what removes threshold 3's stated harm. The live path is a second,
labelled path beside it. Replacing the demo path with generation reopens the ADR.

**2. The next `business_context.md` edit does not block it, and the old argument
does not recur.** q036's fix will change the prompt again, but the path renders
prompts from files at request time and every test in it is a plumbing test
against `StubProvider` — no test asserts anything about what the model produces,
because that is the eval's job (ADR-0005). What the old argument forbade was
validating *generation quality* against a doomed prompt; nothing here does that.

**3. The last link is unproven.** The credential resolves, `/health` reports
`vertex / gemini-3.6-flash`, and no call to a real provider has ever been made
from this code. Everything up to the network is tested; the network hop is not.
One call is ~$0.02.

**Its known limit, which is real:** for a scoped role, the `WHERE` clause is the
model's to write. The scope string carries the predicate (`store_id = 1
(Kothrud, Pune)`, the shape the 47×3 run measured) and `check_scope` sits behind
it, but that tripwire only fires when `store_id` is among the result columns.
Pattern-matching the SQL for the predicate is instance eight's defect and was
deliberately not done; the real fix is a per-store database role, which is not
Phase 1. **Demo mode is unaffected** — there the predicate is substituted rather
than requested.

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
| API query endpoint | part of ~32h | **both halves done** | `POST /query` serves answer + SQL with no key and no quota; the live path generates instead, opt-in, and is proven against the real model (3 calls, ~$0.06) |
| `web/` — Next.js, tokens, typed client | part of ~32h | **query view done** | Built from `docs/DESIGN-TOKENS.md`, which was proposed and not formally agreed — say if the palette or type should change |

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

The eval measures execution accuracy over 49 natural-language questions against
a Postgres retail schema, scored by deterministic result-set comparison — no
LLM-as-judge. Reported three ways: overall, view-covered, not-view-covered, with
thresholds read off the **not-view-covered** number.

**Its dominant failure mode is not the model.** Nine axes of instrument defect
have been found, and the direction never once scatters: **every reference error
has favoured the reference and run against the model.** The cause is structural
— the author knows what they meant, so the reference looks obviously right in
retrospect. Inverted authoring is the preventive fix; the predicate trace is the
verification one.

**The recurring defect class, ten instances:** *a check that is not running,
wearing the label of a check that is.* It has appeared in a column name, an
empty expectation, the matcher, the pre-commit hook, a passing eval row, a
**process rule** (the old stopping rule — worst, because it licensed the others
to stop looking), the conjunct splitter, and **the probes built to hunt the class
itself**.

**Nine and ten, both found 2026-08-08, both in the measurement apparatus:**

- **ADR-0001's reversal test could not fire.** It named "a second full×3" as the
  one fact that would overturn keeping generated SQL. Responses are cached on
  (prompt fingerprint, question id, run index) and the runner iterated indices
  0…runs-1, so repeating the command under an unchanged prompt replays the first
  triple from cache, makes zero calls, and hands back the same 10.6% as
  confirmation. The reversal condition of the project's most consequential
  decision was unfalsifiable by construction. `--run-offset` fixes it, and the
  runner now says so when a multi-run scoring made no calls.
- **Cache invalidation was blind to the question text.** The docstring said
  editing any prompt or context file invalidates the cache — true, and it read
  as complete. The question itself is also an input to the prompt and is not in
  the key, so replacing a question left its old answers live for the next
  re-score to judge against the new question. `question_sha` now closes it,
  with the pre-existing records grandfathered so the fix costs nothing.

**Also fixed, same day:** `evals/results/<date>-sql.json` was written
unconditionally, so a `--limit 5` smoke test could replace a 141-response result
file, and two runs on one day collided. Only a canonical full run at offset 0
keeps that name now, and results files record *which* question ids they ran, not
just how many.

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
| `expected_on` — a schema comment asserting a data property that is false | yes, 2026-08-08 | **2 of 18 checkable claims** — `business_date` "not always equal to the UTC date of `sold_at`" is also false, and 5 other claims held. See the second blind spot above |

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
- **Re-scoring is free; re-running is not.** Responses are cached under the
  prompt fingerprint, and the live one is **`415953964db74b80`** — 141 responses,
  the 47×3 run. (`de60dd5e3dde7787` is the pre-v2 prompt and its 47 responses are
  still on disk; this line named it as current until 2026-08-08, which was
  wrong.) Reference fixes re-score at zero cost. **Any edit to
  `business_context.md` or the prompt voids every cached response** — 49 questions x
  3 runs is 147 calls and ~$3.30 through Vertex. The live path is not cached at all, deliberately: see its
  section above.
- **`AS_OF_DATE = 2026-06-30`, never wall-clock.** `current_date` is forbidden
  in generated SQL.
- **Credentials never enter the repo.** `make hooks` installs a pre-commit
  content scan; history has been verified clean.
