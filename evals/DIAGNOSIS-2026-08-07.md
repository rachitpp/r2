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

## Re-verification of this file's own numeric claims

The q019 entry recorded a hand-verification **that never ran** (see below). Every
numeric claim in this file was therefore re-executed against the database from
the cached responses. **Zero model calls.** Two checks were run: each individual
claim, and — as a wholesale control — the scorer re-run over all 47 cached
responses and compared to the recorded outcomes.

| claim | verdict |
|---|---|
| **q019 returned 8.23 / 6.73, "verified by hand"** | **FALSIFIED.** Returns **8.30 / 7.08**. Both recorded figures are constants published in `business_context.md` lines 122–123. |
| q018 split at 2025-09-22 unprompted | **VERIFIED.** Pre-reform rate is **8.23 exactly**, and it matches the published constant because the model genuinely filtered from 2025-07-01 — the published window. Its post-reform figure is **7.08, not the published 6.73**, so it did *not* echo the constants. |
| tolerance's returns trap, 54,759 gross vs 54,594 net | **VERIFIED EXACT.** q009 over May 2026: gross 54,759, returned 165, net 54,594 — a 0.301% gap. Chain-wide the figures are 965,408 / 963,062; the docstring is scoped to the trap question, not the chain, and is correct. |
| q001 passed by an unsound route | **VERIFIED.** Model omits `below_reorder_point`, uses `days_of_cover IS NOT NULL`, and returns the identical 10 rows. |
| q026 reference runs in 0.10s | **VERIFIED** — 0.09s. |
| q026 model runs in 1.59s | **NOT REPRODUCED — 5.33s.** Timings are machine- and cache-dependent, so this is a soft discrepancy, not a falsification. The conclusion **strengthens**: it exceeds the 5s `statement_timeout` outright rather than "compounding past" it. |
| — | **New:** run without that timeout, q026 returns `wrong_rows`. It is **wrong as well as slow**, so "semantically plausible, operationally unusable" was too generous. |

**Wholesale control: 46 of 47 cached responses reproduce their recorded
OUTCOME** — `correct` / `wrong_rows` / `execution_error`, not their values. The
single divergence is q026, an artifact of the re-run connecting as a role
without the 5s timeout, which is itself the confirmation above.

**Read what that control does and does not cover.** It vindicates **the
scoring**: the harness, applied to the cached responses, still lands where it
landed. It does **not** vindicate **the audit trail**, and it structurally
cannot. The q019 defect was a wrong *value* inside a *correct outcome* — the
bucket was `instrument` before and after — so outcome-reproduction was never
capable of detecting it, and would not have flagged it however many times it
ran. Only the per-claim re-execution in the table above reaches that class.

Stated plainly: **the measurement is sound; the prose describing it was not, and
it took a different check to find that out.** Two checks, two scopes; the
stronger-sounding number is the weaker of the two.

### What the q019 entry actually was

`business_context.md` publishes 8.23% and 6.73% as the true effective rates
either side of the reform. Those two constants were written into the
**observed-value** slot, and a hand-verification was then asserted over them.

That is the project's recurring defect class in its purest form — **a check that
is not running, wearing the label of a check that is** — and it had migrated out
of the code, where the eval harness exists to catch it, and into the diagnosis
record, where nothing was looking. The instrument's own audit trail was the one
artifact with no instrument pointed at it.

The general rule this earns: **a recorded observation that equals a published
constant is not evidence, it is a coincidence requiring proof.** Both surviving
matches above (q018's 8.23, q009's 54,759) were re-executed for exactly that
reason, and both hold.

---

## A seventh axis — CORRECTED: it is row identity, not invented labels

> **The original statement of this axis rested on a false claim, and its
> evidence base was wrong in 3 of its 4 questions. Both are corrected below.
> The axis is real; it is not the axis that was written down.**

### The false claim

The previous revision reported that q019 returned **8.23 and 6.73, identical to
the reference**, and was scored wrong on label text alone. It says so twice, and
says it was "verified by hand".

**It is not true.** Re-executed against the database from the same cache entry:

| | reference | model |
|---|---|---|
| label | `before` | `Before Sep 22, 2025` |
| rate | **8.23** | **8.30** |
| label | `from 22 Sep 2025` | `From Sep 22, 2025 onwards` |
| rate | **6.73** | **7.08** |

The numbers **differ**, and the cause is not presentation. The reference
restricts to `business_date BETWEEN 2025-07-01 AND 2025-11-30`; the model used
all history. q019 is still `instrument` — `business_context.md` says an unstated
period means **all the history there is**, so the model followed the stated
default and the reference silently narrowed — but it is the **q045 defect**
(reference contradicts a published definition), not the label defect. The label
was never the cause.

### The evidence base

Re-checked question by question, comparing values not labels:

| id | numbers match? | what actually differs |
|---|---|---|
| q019 | **no** — 8.30 vs 8.23, 7.08 vs 6.73 | period scope; reference narrowed an unstated period |
| q022 | **yes** — 179444 / 133277 exact | a genuinely invented `CASE` label |
| q024 | **yes** — 3238251.00 / 20997 exact | reference invented `'Holi 2025'`; model returned `festival_id` + `festival_date` |
| q042 | **yes** — every row and unit exact | `stores.code` (`ST-01`) vs `stores.name` (`Kothrud`) — **two real data columns** |

So only **q022** is "a free-text label the query invents". q042 is two
legitimate columns of the `stores` table, and by this file's own rule — "a
supplier name from `suppliers` is **data**" — it was never the label axis at
all. In q024 it is the *reference* that invented the display string while the
model returned identifying data.

### What the axis actually is

**The question does not determine which column identifies a row.** `ST-01` or
`Kothrud`; `festival_id` or a rendered `'Holi 2025'`; an invented period caption
or the boundary date itself. All name the same row. Only q022's case is a string
with no underlying column at all.

That is a wider defect than "labels are presentation", and it is not fixed by
dropping labels from `answer_columns` alone — q042 needs *either* store column
to satisfy the identity, which is a matching rule, not a projection rule.

**Fix (still 1 of the 10), restated:** identity columns are satisfied by any
column that identifies the same row, and a pure display string leaves
`answer_columns` with order carrying which row is which. The fix as originally
written would have passed q022 and q024 and **left q042 failing.**

---

## Failures — diagnosed

| id | bucket | reasoning |
|---|---|---|
| q019 | `instrument` | **Re-diagnosed — the previous entry was factually wrong.** Numbers are *not* identical: 8.30 vs 8.23 and 7.08 vs 6.73. Reference narrows to `business_date BETWEEN 2025-07-01 AND 2025-11-30`; the question names no period and `business_context.md` says an unstated period means all available history. Model followed the stated default. Same defect as q045, not the label defect. **Temporal split itself correct** — 2025-09-22, unprompted. |
| q022 | `instrument` | Numbers exact (179,444 / 133,277). A genuinely invented `CASE` caption — the only clean instance of the label axis in the set. |
| q024 | `instrument` | Numbers exact (3,238,251.00 / 20,997 and 3,370,469.20 / 21,563). The *reference* invented `'Holi 2025'`; the model returned `festival_id` + `festival_date`, which identify the same rows. Row-identity axis. |
| q042 | `instrument` | Every row and unit exact. `stores.code` (`ST-01`) vs `stores.name` (`Kothrud`) — **two real data columns**, so by this file's own data/presentation rule it was never the label axis. Row-identity axis. |
| q026 | `model` | Correlated `EXISTS` inside aggregate `CASE`, three times over. 1.59s where the reference is 0.10s; compounds past the 5s statement timeout. Semantically plausible, operationally unusable. The context document cannot teach query planning, and nothing about the question invited that shape. First unambiguous model failure. |
| q004 | **`context`** | **Re-bucketed from `ambiguous`; reasoning below.** Question names an explicit threshold ("less than three days"). Reference required `below_reorder_point` as well; model instead added `on_hand > 0`, excluding the 11 already-at-zero lines the reference returns. Both queries carry an unstated predicate. `business_context.md` says "if a question gives its own number … that number wins" but never says whether the number *replaces* the reorder-point default or *adds* to it, nor whether a reorder question covers lines already at zero. |
| q011 | `instrument` | Grain of the velocity filter is unstated. Reference applies `units_per_day > 1` **per store row**, then sums stockout days **chain-wide** — a mixed grain the question never asks for. Model applied one grain throughout (`HAVING sum(units_per_day) > 1`). **Isolated:** re-running the reference with only that predicate changed reproduces the model's ordering exactly, so the grain is the sole cause. |
| q012 | `instrument` | **The LIMIT boundary falls inside a tie.** At Pune the stockout counts run 8→2, 7→1, 6→3 products — six above the line — then **five products tie at 5 days** for the remaining four slots. Which four is not determined by the question. Reference broke it by `p.sku`, model by `units_per_day DESC`. The tiebreak changes *membership*, not just order, so the question has no single correct answer set. |
| q015 | `instrument` | Reference filtered `new.payment_terms_days <> old.payment_terms_days` — narrowing "which suppliers renegotiated" to "which changed their payment terms". Gokul Dairy genuinely renegotiated on 2025-12-09 (min order 12,000→15,000; volume discount 1.50→3.00) with payment terms held at 30. The model's twelfth row reports that correctly. The question asks who renegotiated; the reference answered a narrower one. |
| q031 | `instrument` | **Reference ordered by a rounded column.** `round(…, 1)` maps STP-0028 (12.0368%) and STP-0007 (12.0467%) both to 12.0, manufacturing a tie that the data does not contain, then broke it by `sku` — placing the *higher*-margin line first. Same 10 rows; the model ranked on the true values and its order is strictly more accurate. |
| q035 | `instrument` | Reference `GROUP BY pr.name` **conflates distinct promotions that share a name.** There are 46 promotions under 32 names; "Atta, Rice & Dal — 25% off" is three separate campaigns (Aug–Sep 2025, Nov–Dec 2025, Jan–Feb 2026) with different windows, merged into one row of 953 units. "For each promotion" means each row in `promotions`; the model grouped by `promotion_id` and kept them apart. The reference's answer cannot distinguish three campaigns. |
| q043 | **`model`** | Reference `avg(total)` = 717.34, model `avg(subtotal)` = 666.66. `business_context.md` is explicit: "`sales.total` … **what the customer actually paid**", and "only use `total` when the question is about cash collected, banking, or what a customer paid." A basket "coming to" a figure is what was paid. The context gave the model exactly what it needed and it used the net-of-tax column anyway. The other column, `transactions_per_day`, matches under tolerance (387.63 → 387.6). **Second unambiguous model failure.** |
| q045 | `instrument` | **The reference contradicts the context document's own definition.** `business_context.md` defines *about to run out* as **fewer than 7 days of cover**, and *running low* — a separate phrase — as at or below the reorder point. The question says "about to run out"; the reference required `below_reorder_point` as well. **Isolated:** `<7` vs `<=7` changes nothing (no product sits at exactly 7.0), so all 10 extra rows come from that added predicate. The model applied the published definition of the phrase the question used. |
| q047 | `instrument` ×2 | Same rounded-ORDER-BY defect as q031: TEA-0027 (3.0848%) genuinely outranks DRY-0005 (3.0545%), both round to 3.1, and `sku` inverted them. **Plus an eighth axis** — the model returned the share as a fraction (0.0501) where the reference used a percentage (5.0). Same 10 products either way. |

## An eighth axis: the magnitude of a ratio

"Which sold the largest **share** on promotion" fixes the ranking and says
nothing about whether the answer is `0.05` or `5.0`. Both are the share. The
reference picked percent, the model picked fraction, and `tolerance.py` compared
them at one decimal place — 5.0 against 0.1 — and called it wrong.

This is the label axis one level down: **presentation the question does not
determine, sitting in the value position where it gets compared.** A `pct`
column name already routes to `Kind.RATE`; what it does not do is reconcile a
ratio expressed against a different base.

## A ninth axis, and the worst of them: disambiguation is unscoreable as written

`scoring.py` scores `expects: disambiguation` on **"whether the reply states
which reading it took"**. `sql_generate.md` line 6 instructs the model:
**"Return only SQL. No explanation, no markdown fences, no commentary."**

The criterion is **unmeetable by construction**. The model is forbidden from
writing the prose it is then judged for not writing. All three disambiguation
questions — q003, q018, q027 — are in this state, and no amount of model skill
resolves it.

It also undercuts the one result the run was most encouraged by. q018 "stated
its reading" **only through its `CASE` labels** (`'Pre-reform (2025-07-01 to
2025-09-21)'`) — which is exactly the presentation the seventh-axis fix strips
out of comparison. **The instrument ignores invented labels when scoring rows
and depends on them when scoring disambiguation.** q003 and q027 emitted bare
SQL with no comment and could not have passed whatever they were doing.

The finding about q018 survives on its own terms: it split at 22 September
unprompted, which is the correct behaviour and the GST teaching working. What
does not survive is scoring it — or its two siblings — against a criterion the
prompt forbids.

### RULING — restated on the corrected premise, deliberately NOT implemented

> The ruling was first taken against axis 7 as "free-text labels". **That premise
> has been withdrawn** — the axis is row identity, and q042 was never on it. The
> rationale below is re-derived from scratch on the corrected axis. The
> conclusion survives; it now rests on reasoning that is actually true.

**Under the corrected axis, the contradiction is sharper, not weaker.** Row
identity says: *which column names a row is not determined by the question, so
any column that identifies the same row satisfies it.* Disambiguation scoring
says: *the caption reveals which reading was taken, so read it.* q018 sits on
that seam — it is credited with declaring its reading through the very
`CASE` strings row identity exists to normalise away. Under row identity,
`'Pre-reform (2025-07-01 to 2025-09-21)'` and `MIN(business_date)` name the same
row, so discarding the string is the axis working correctly, not a gap in it.

**Ruled: identity is not signal. A reading is read off the predicate.** The
artifact under test is a query. Which reading it took is a fact about what it
*computes* — its `WHERE`, its `GROUP BY`, its join condition — not about what it
captions. This is now the same rule the row-identity axis already applies to
scoring rows, rather than a second rule bolted alongside it. **One rule, two
uses**, which is why the contradiction disappears rather than moving.

Re-derived consequences:

- **q018 re-adjudicates on `business_date < DATE '2025-09-22'`.** That predicate
  is the declaration, and it is verified above as genuinely present and
  genuinely correct. Verdict unchanged; grounds now sound.
- **q003 becomes scoreable** on `below_reorder_point` — that predicate is its
  reading of "needs attention", declared in the only place a query can declare
  anything.
- **q027 becomes scoreable** on the *absence* of a per-store baseline: it summed
  raw festive revenue, and that is the reading. Note this only works under the
  restated rule — the original label-based rule could not have scored q027 at
  all, because it emitted no caption to read. **The corrected premise scores a
  question the original one could not**, which is the strongest evidence the
  restatement is right rather than merely surviving.
- **No prompt change.** `sql_generate.md` keeps "return only SQL", so the freeze
  at `de60dd5e3dde7787` holds and **the $0.99 run stays valid.**

**Not implemented, on purpose.** `scoring.py` is unchanged — see the instrument
v2 decision below, which changes what "not yet" is protecting.

## An accounting gap in this file's own count

The previous revision listed **seven** undiagnosed failures and named them.
There were **eight**: `q043` appears in `stats.overall.silent_wrong` and in
neither table. A file whose first rule is that an unexamined question is marked
`undiagnosed` had one that was not marked at all. Recorded here rather than
quietly corrected, because the miscount is the kind of thing this file exists to
catch.

## q043 is a bucket FLIP, not a fresh finding

The previous revision carried q043 nowhere at all — but the run it describes
already contained it, and the four-bucket discipline means an unexamined
question is `undiagnosed`, not absent. Recording it now as **`model`** is
therefore a **flip from an implicit `instrument`-shaped silence to an explicit
model failure**, and it moves the count in the unfavourable direction: model
failures go from 1 to 2. Flagged as a flip so nobody later reads it as a new
defect discovered on a second pass.

## The rotation process let a known defect through — q045

q045 was already identified as a reference-author error during the five
rotations. Its reference has been modified **three times**:

| commit | reference predicate |
|---|---|
| `3210570` eval runner built | `below_reorder_point AND on_hand > 0`, `LIMIT 20` |
| `e68f950` result_shape taxonomy | `on_hand > 0 AND below_reorder_point AND days_of_cover < 5` |
| `1045fdb` **rotation 5** | `on_hand > 0 AND below_reorder_point AND days_of_cover <= 7` |

Rotation 5 **did touch this exact predicate** — it moved the cover threshold to
7 to match the "about to run out" definition. It did not notice that
`below_reorder_point` is the definition of a *different* published phrase
("running low"), and left it in place. It also wrote `<= 7` where the definition
says *fewer than* 7.

So the defect was not missed. **It was half-fixed**: the visible half (the
number) was corrected against `business_context.md`, and the structural half
(an extra predicate belonging to another definition) was not — by an edit that
had the definition open at the time.

**This is a gap in the rotation process, not in q045.**

### Checked: the half-fix pattern is NOT systemic

The signature is greppable — a commit changing a literal or comparator inside a
reference's `WHERE`/`HAVING` while leaving the predicate's identifier structure
untouched. Every reference edit across all 8 commits that touched
`questions.jsonl` was diffed that way. Git only, no model calls.

Four candidates; **three are not the pattern**:

| id | edit | verdict |
|---|---|---|
| q045 @ `1045fdb` | `< 5` → `<= 7`, `below_reorder_point` left | **the pattern** — the only instance |
| q005 @ `e68f950` | `on_hand <= 5` → `<= 2` | **legitimate** — the question says "2 units or fewer"; the threshold was aligned to the number the question names |
| q012 @ `395e6e9` | `stockout_days_30d >= 3` → `> 0` | **legitimate** — removed an invented filter the question never mentioned |
| q017 @ `1045fdb` | flagged on a `round(…,1)` literal | **false positive** — the real edit replaced `v_supplier_terms_current` with `supplier_terms … AND t.valid_period @> po.ordered_on`, a full point-in-time re-derivation. The opposite of a half-fix. |

So **q045 is one occurrence, not a class.** The hypothesis it suggested does not
survive contact with the history, and is withdrawn rather than left standing on
a single case.

### What the archaeology found instead: coverage, not depth

Tracing the edit history of all 14 failing references:

- **8 of 14 were never revised after authoring** — q015, q019, q022, q026, q031,
  q042, q043, q047.
- **6 of 14 were revised at least once and failed anyway** — q004, q011, q012,
  q024, q035, q045.

The rotation process's weakness is **reach, not thoroughness**. Where it touched
a reference it mostly corrected it properly; it simply never reached most of
what was wrong. Rotation 5's stopping rule was "coverage complete", meaning
every question had been model-tested — but a question can be model-tested,
agreed, and still carry a reference that is wrong in a way the model's single
answer did not happen to expose. **Agreement is not verification**, and eight
references passed on agreement.

That reframes the fix: not "re-derive predicates more carefully during rotation"
but "one model answer per question is too thin a check to harden a reference
against". It is also the strongest argument for the fresh-question ledger and
for inverted authoring, both of which attack reach.

### A correction to the record while here

`evals/README.md` lists q043 among four references "found wrong". Its
`reference_sql` was **never edited**. What rotation 4 changed was the
**question** — "How many transactions…" became "**Since the start of April**,
how many transactions…", naming the period the reference had always filtered on.
So q043's known defect was real and was fixed, on the question side. Its failure
in the measured run is an unrelated axis (`subtotal` vs `total`) and is the
model's, not the reference's.

## Needs-review — diagnosed

| id | bucket | reasoning |
|---|---|---|
| q018 | **model passed the trap** | The blended-rate trap. The model split at 22 September unprompted. That is correct behaviour and the GST teaching in `business_context.md` working. **Pending re-adjudication on its predicate** rather than its `CASE` strings — see the ruling below; the verdict is not expected to change, but the grounds must. |
| q003 | `instrument` | Bare SQL, no stated reading — as instructed. Scored against a criterion the prompt forbids. See the ninth axis. |
| q027 | `instrument` | Same. Answered raw festive revenue rather than uplift against each store's own baseline, which *is* the ambiguity the question was rewritten to carry — but nothing in a SQL-only reply can declare which it chose. |

## Passes — audited

| id | bucket | reasoning |
|---|---|---|
| q001 | `instrument` | **Passed by an unsound route.** Model omitted `below_reorder_point`; ordering by ascending cover and taking 10 happens to surface the same rows. Shift the data and the answers diverge. Also reveals a fifth reference-author error: the question never mentions the reorder point, so the reference encoded an unstated assumption. **A pass hiding a defect in both directions.** |
| q007, q013, q016, q020, q021, q030, q040, q046 | `sound` | Read by eye. Correct answers by defensible routes. q020 joins `gst_rates` twice at either side of the reform date rather than walking the supersedes chain — different from the reference and arguably better. |

## Passes — the remaining 21, audited

**All 30 passes have now been read.** Both queries executed, rows read against
the question's exact words, zero model calls. The prediction from the 1-in-9
sample was "roughly 2 more hiding something"; the actual count is **2**, though
neither is the failure mode that was expected.

**19 of 21 are sound**, several impressively so: q023 refused a Diwali-over-
Diwali comparison and *verified the impossibility from the data* ("only covers
January 2025 to June 2026 … only one Diwali"), which is the real coverage window;
q044 used the `OUT OF SCOPE` sentinel rather than conflating it with a schema
gap; q034 read the timezone from `stores.timezone` where the reference hardcoded
`Asia/Kolkata`, which is the more robust route and identical here; q017 — the
reference rotation 5 fully re-derived — matched on both sides of a
`valid_period @> po.ordered_on` join.

### The two findings

| id | verdict | detail |
|---|---|---|
| **q005** | **stale `intent`** | Passes soundly — predicates are byte-identical. But its `intent` still reads "Explicit threshold overrides the reorder point: **`on_hand <= 5`**" while both the question ("2 units or fewer") and the reference say `<= 2`. |
| **q008** | **latent reference defect** | Model correct and rows identical. The *reference* carries `HAVING sum(units_sold) > 200` — a volume floor the question never mentions. Currently inert: the lowest `units_sold` anywhere near the answer is **1,713** against a floor of 200. Never revised. Same family as q001 — an unstated choice sitting in a reference nobody revisited. |

### q005 is a second instance of the half-fix — in the record, not the predicate

The predicate half-fix hypothesis was withdrawn on the evidence, correctly: one
instance. But `e68f950` changed q005's **question** ("under 5 units" → "down to
2 units or fewer") **and** its **reference** (`<= 5` → `<= 2`) in lockstep, and
left `intent` describing the superseded threshold. Two of three coupled fields
updated; the third stale.

**That is the q045 shape one field over**, and it lands somewhere that now
matters more than it used to: the disambiguation ruling above makes `intent` the
field a human reads when hand-scoring q003, q018 and q027. A stale `intent` is a
stale scoring criterion. q005's is demonstrably stale; **no other `intent` field
has been checked against its own question and reference.**

### Class-level findings

- **`is_active = true` is a structural no-op — all 600 products are active.** It
  appears in many generated queries (q002, q008, q011, q012, q031, q039 …) and
  cannot change any answer in this dataset. Harmless today, invisible to the
  instrument, and it would silently move several answers the moment the seed
  introduces an inactive product. An unstated predicate the eval is structurally
  unable to detect.
- **No pass echoes a published constant.** Checked specifically, given how the
  q019 entry failed. q009's 54,759 / 54,594 is the sole match and is legitimate
  — that question *is* the source of the figure the tolerance docstring quotes,
  and it was re-executed rather than assumed.
- **"Never revised" does not predict unsoundness.** 13 of the 21 were never
  revised and 12 of those are sound. Agreement-without-revision is not evidence
  of a *bad* reference — but nothing about it is evidence of a good one either,
  which is exactly the null-result problem the stopping rule has.

---

## What is established so far

**All 14 failures are now diagnosed.**

- **11 of 14 are instrument**, across six distinct defects — **not four on one
  axis plus seven, as the previous revision framed it.** Re-examination split
  the "label axis" apart: only q022 is an invented caption; q024 and q042 are
  **row identity** (which column names a row); and q019 is not a label defect at
  all but a **reference contradicting a published definition**, the same defect
  as q045. The rest: under-determined grain (q011), a LIMIT boundary inside a
  tie (q012), a reference narrower than its question (q015), ordering by a
  rounded column (q031, q047), and grouping distinct promotions by name (q035).
- **2 of 14 are unambiguously model** — q026 (unusable query plan) and q043
  (`subtotal` where the context explicitly names `total`).
- **1 of 14 is `context`** (q004) — **re-bucketed from `ambiguous`, against the
  favourable direction.** The previous revision was self-contradictory here: the
  table said `ambiguous` while its own reasoning cell said "context gap …
  candidate for a context fix". `ambiguous` should mean two readings **no context
  document could settle**. This one is settleable in a sentence — does an
  explicit cover threshold replace the reorder-point default or add to it, and
  does a reorder question include lines already at zero? — so by the bucket
  definitions it is `context`, which means `business_context.md` is incomplete.
  Recording it as `ambiguous` charged the defect to the question instead of to
  the deliverable. **No context gap was absorbed into `instrument`**; the count
  is 11 + 2 + 1 = 14 with q004 standing alone.
- **All 3 needs-review are instrument**, on a criterion the prompt forbids the
  model from meeting.
- **1 of 30 passes was unsound** (q001), and it also exposed a reference error.
- **21 passes remain unaudited.**

**Five more reference-author errors**, and — as before — **every one favours the
reference and runs against the model.** None the other way. That now stands at
roughly ten, and a defect that never once scatters in the other direction is not
noise; it is the authoring order, which is what inverted authoring exists to fix
and what these questions predate.

### The temporal cluster — REOPENED, then closed on evidence

The previous revision closed this on q015 alone. That was not sufficient, and
the objection is the project's own recurring defect class: **a label mismatch
fails the comparison before anything examines the temporal predicate.** A
cheaper check failing first is not evidence that the expensive one passed. For
q019, q022 and q024 the temporal logic had never actually been looked at.

So it was looked at — the generated SQL read directly, and the temporal
predicate assessed on its own terms, independent of how the row was scored:

| id | temporal construct used | correct? |
|---|---|---|
| q019 | `business_date < DATE '2025-09-22'` split, unprompted | **yes** — right boundary, right side. The divergence is *period scope*, not point-in-time reasoning |
| q022 | `JOIN gst_rates g ON … AND g.valid_period @> d.business_date` | **yes** — the exact required pattern, and the numbers land exact (179,444 / 133,277), so the join is confirmed by result and not merely by shape |
| q024 | `JOIN festivals f ON d.business_date BETWEEN f.ramp_start AND f.ramp_end` | **yes** — took the window from the `festivals` table rather than inventing dates, and resolved both instances across years (2025-03-14, 2026-03-04) with exact revenue and units |
| q015 | walked `supersedes_id` old→new | **yes** |

**Conclusion unchanged, but now actually earned.** No question in the cluster
reached for `current_date`, hardcoded a window where a lookup was required, or
compared across a boundary without splitting at it. q022 and q024 land their
numbers *exactly*, which a wrong temporal predicate cannot do by accident.
Combined with q018 splitting unprompted and q020 joining `gst_rates` either
side, there is **no evidence in this run of a point-in-time reasoning deficit.**

What the re-examination *did* find is that the closure had been resting partly
on a false claim about q019 (see the corrected seventh axis). The conclusion
survives; one of its supports did not.

### What this does to the number — a projection, not a result

Of the **10** not-view-covered failures, **8 are instrument** and 2 are model
(q026, q043). Correcting them would move not-view-covered from 23/33 to **31/33**.

That figure is **not reported anywhere and is not a measurement.** It is what
the arithmetic implies if every diagnosis here is right, and it has to be earned
by re-scoring against corrected references — not asserted from this file. It
can also move **down**: 21 passes are unaudited and 1 of the 9 sampled was
unsound.

What is safe to say now is narrower and more useful: **the raw 69.7% measures
the instrument at least as much as the model**, which is why it was never acted
on.

## Fix budget for this round

Used: **1 of 10** — the label axis. Diagnosis of failures is now complete, so
the remaining fixes are unblocked. Distinct defects to correct, ~7 more:

1. Ordering by a rounded column (q031, q047) — one defect, two questions.
2. LIMIT boundary inside a tie (q012).
3. Under-determined filter grain (q011).
4. Reference narrower than its question (q015).
5. Grouping distinct promotions by name (q035).
6. **Reference contradicting a published definition — q045 AND q019.** One
   defect, two questions: q045 borrowed a predicate from a neighbouring
   definition, q019 narrowed a period the question left unstated. Both
   contradict `business_context.md`.
7. Ratio magnitude, fraction vs percent (q047).
8. Row identity — which column names a row (q024, q042). **Not covered by the
   label fix as originally written**, which would have left q042 failing.
9. Disambiguation scoring — **ruled above, not implemented.** `scoring.py`
   unchanged; no prompt change, so the freeze and the run both hold.

That is at the cap of 10 with one spare. **Item 9 is not a reference fix and
item 6 is now two questions**, so the accounting only works because items 1, 6
and 8 each close two questions with one correction.

**A fix not on this list:** q004 is `context`, so it is an edit to
`business_context.md` — which **voids the prompt fingerprint and all 47 cached
responses.** It must not be bundled with the reference fixes. Reference fixes
are free to re-score; a context edit costs another $0.99 run. Sequence them:
reference fixes and re-score first, context edit second and deliberately.

**The 21 unaudited passes should be audited before any of this is applied** —
a fix that lands mid-audit voids the comparison in exactly the way this file
was written to prevent.

---

## PENDING DECISION: declare instrument v2 and drop the cap

**Recorded, not acted on.** Per the rule that a ruling is taken in a separate
sitting from the evidence that prompted it, this is written down for a later
decision rather than applied on first sight.

### The cap no longer protects anything

The fix budget exists for one purpose: to keep this measurement comparable to
the next one. That purpose is **already void**, and not by accumulation:

- **q004 is bucketed `context`**, so its fix edits `business_context.md`, which
  **changes the prompt fingerprint and voids all 47 cached responses.** The
  re-measure is committed the moment that fix lands, whatever else is or is not
  done. Roughly $0.99 and about 2.3 days at 20 RPD.
- With the re-measure already owed, rationing fixes to stay under ten buys
  **nothing except the appearance of an intact run.** That is favourable
  rounding one level up — at the process rather than the number.

### The instrument has already changed beyond the threshold

Independently of the cap, what has accumulated is not a tuned instrument:

- **11 instrument defects in 14 failures.**
- **An axis redefined** — axis 7 is row identity, not labels, and its evidence
  was wrong in 3 of its 4 questions.
- **A falsified verification in the diagnosis record**, which is a defect in the
  audit trail rather than in a reference.
- **1 unsound pass in 9 sampled**, with 21 unread.
- **A scoring contract to be rewritten** (the disambiguation ruling).

The rule says void the run **deliberately, not by accumulation.** Deliberately
is available right now. Accumulation is what happens if the last slot is spent
and work continues regardless.

### Recommendation

1. **Declare instrument v2 explicitly** and mark the 47×1 as v1 — measured,
   diagnosed, superseded. It keeps its value as the run that found the defects;
   it stops being a baseline anything is compared against.
2. **Drop the fix cap for the remainder of the audit.** It is protecting a
   comparison that no longer exists.
3. **Finish all 21 unaudited passes without budget pressure** — the pass audit
   is where the remaining unknown is, and the cap was actively discouraging it.
4. **Batch every fix**: references, the scoring contract, the context edit.
5. **Re-measure once, against v2.** One $0.99 run, not two.

### REVISED — "drop the cap" is withdrawn; the gate replaces it

The counter-argument was accepted: the cap's **stated** purpose was
comparability, but its **working** effect was discipline — it made "fix it and
see" expensive, and that is what produced this file rather than a pile of
retuned references.

So v2 does not drop the cap, it **replaces it with an enumerate-then-fix gate**:

> **No fix is applied until enumeration is complete. Then all fixes land in one
> batch.**

This keeps the expensive-to-guess property that was doing the real work, and
drops only the arbitrary number that no longer protects a comparison. It also
scales, which the cap did not: a round finding twelve defects is not forced to
either stop at ten or void itself.

The gate has now been demonstrated twice in this file — failures were enumerated
before any fix, and the 21 passes were enumerated before any proposal — both
times finding defects that a fix-as-you-go pass would have buried under its own
edits.

**Recommendation as it stands for next sitting:**

1. Declare **instrument v2**; mark the 47×1 as v1 — measured, diagnosed,
   superseded. It keeps its value as the run that found the defects.
2. Replace the fix cap with the **enumerate-then-fix gate**.
3. Apply the **predicate-to-words trace** to all 47 references (see
   `README.md` → *When to stop rotating*). It is the new stopping rule and it
   has not yet been run against anything except retrospectively.
4. Batch every fix: references, the scoring contract, the context edit.
5. Re-measure once against v2.

**Nothing here is implemented.** Decision to be taken in a separate sitting from
the evidence that prompted it.

## Note on runs 1 and 2

If diagnosis changes `business_context.md`, the run-0 prefix is void and gets
re-spent. That is the argument for finishing diagnosis **before** buying runs 1
and 2, not after.
