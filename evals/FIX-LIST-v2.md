# Fix list for the instrument v2 sitting

> ## STATUS 2026-08-08 — thirteen fixes APPLIED, free re-score taken
>
> The mechanical items are done and re-scored at **zero model calls, 47 cache
> hits, 0 misses**. **No regressions**: q015 and q045 now pass, nothing that
> passed before now fails, and q011 moved `wrong_rows` → `wrong_order` — the
> grain fix landed and only its boundary tie remains.
>
> **not-view-covered moved 23/33 → 27/33 (81.8%, CI 66–91%).** The interval does
> **not** exclude 85%, so ADR-0001 threshold 2 does not fire. That is *not* a headline number and
> the retirement still stands: the batch is incomplete, the four forks below are
> undecided, and `full×3` has not run. It is an interim re-score, nothing more.
>
> **Then the identity fork was decided and applied too.** q019, q022 and q024
> moved to an ordered shape with the invented label out of `answer_columns` —
> the fix the diagnosis had already prescribed. **q042 was made consistent with
> its six siblings (`stores.name`) rather than loosening the matcher to accept
> either identifier**, because loosening would mask genuine identity errors
> everywhere else. q030's intent now names the reading it is scored against.
> Five questions fixed in total: q015, q019, q022, q024, q045.
>
> **What is left, and it is now only three things:** the **tie class** (q011,
> q012, q042 — item 14), which needs `expected` to carry the tied alternatives
> and so is a schema change to the measurement artifact, not a decision;
> **q004** (item 12), which spends ~$0.99 and ~2.3 days of quota and is
> therefore yours under "ask before anything that repeatedly spends quota"; and
> the two genuine model failures, q026 and q043, which no instrument fix
> reaches.
>
> ### UPDATE 2026-08-09 — that list is closed, and its last line was wrong
>
> **q004 was applied** in the instrument v2 batch, and the quota it needed was
> spent (prompt re-frozen twice since; 288 responses bought). **The tie class is
> handled** — tie-completion lives in `scoring.py`, and q042 now scores as "a
> valid completion of ties the question does not break".
>
> **"The two genuine model failures, q026 and q043, which no instrument fix
> reaches" did not survive contact with more runs, and neither half of it held.**
>
> - **q043** is `correct 3/3` on the current prompt and was `correct` once in six
>   runs of the previous one. It described one triple, not the system.
> - **q026** was reached by an instrument fix — **item 16, the one deferred as
>   "needs *the festive season* defined in data terms"**. Defining it *was* the
>   fix: the question now names the Navratri, Dussehra, Dhanteras and Diwali ramps
>   and the reference reads their dates from the `festivals` table like q024 and
>   q025. Its silent-wrong disappeared; what is left is a statement timeout in all
>   three runs, which is a visible failure and not a silent one.
>
> **Item 16 is therefore applied**, and the deferral note above should be read as
> history. The remaining q026 finding — that the model's festive-membership idiom
> is too expensive at category grain — is real, stable, and the only failure of any
> kind left in the set.
>
> **It was thirteen, not the sixteen claimed.** Three of the "unambiguous"
> sixteen were not: q026 needs *the festive season* defined in data terms,
> q014's fix requires editing a question — which desynchronises its cached
> response rather than merely costing a call — and item 11 needs a new
> per-question field naming each reading's predicate before the ruling can be
> implemented. All three are recorded below as deferred, not done.

**Decision artifact. The four forks and the framing call are not applied.** **ENUMERATION TERMINATED** —
47 questions diagnosed, all 30 passes audited, all 47 `intent` fields checked,
every known singleton checked as a class, and the predicate trace run to
**stationarity at iteration 5**: a full re-run under one validated parser added
no new clauses and no new findings.

Reasoning for each item is in `evals/DIAGNOSIS-2026-08-07.md`. This page exists
so the decision can be taken without re-reading it. **Every status, severity and
cost below is as of iteration 5.**

> **Numbering is stable, and two numbers are vacant on purpose.** **13** was the
> `is_active` gate, renumbered to 20 so the list reads in order. **15** was
> retracted, not deleted — see below. Numbers are not reused, so references from
> the diagnosis file stay valid.

---

## The run is void by enumeration, not by budget

The fix cap was 10 per round, with 1 spent. Enumeration completed the list and
**pushed it past the cap on its own** — first the pass audit (q008, q005's stale
`intent`, the `is_active` blind spot), then the predicate trace (items 14–19),
then the class checks (21, 22). **Twenty live items against a cap of ten.**

That matters for how the cap's rule reads. It says void the run **deliberately,
not by accumulation**. Nobody spent a budget to get here: the list exceeded the
cap because enumeration finished and reported honestly. **This is the deliberate
case the rule contemplates**, arriving on its own terms.

---

## The two costs

Every fix falls into one of these. It is the only distinction that drives
sequencing.

| | what it touches | cost |
|---|---|---|
| **FREE** | `questions.jsonl`, `scoring.py`, `tolerance.py` | Re-score against the existing cache. **£0, minutes.** |
| **VOIDING** | `business_context.md`, `sql_generate.md` | Changes the prompt fingerprint, **voids all 47 cached responses**. ~$0.99 and ~2.3 days at 20 RPD. |

**Only item 12 (q004) is unavoidably voiding.** Everything else re-scores free
*as proposed* — but items 14 and 22 each have an alternative form that voids the
affected questions. Those are flagged at the item, not assumed away.

---

## The list

### FREE — reference fixes (`questions.jsonl`)

| # | defect | questions | what's wrong |
|---|---|---|---|
| 1 | Ordering by a rounded column *(see also 19, 21)* | q031, q047 | `round(…,1)` manufactures a tie the data does not contain, then `sku` breaks it — inverting the true order. STP-0028 (12.0368%) is genuinely worse than STP-0007 (12.0467%). |
| 2 | LIMIT boundary inside a tie | q012 | Six products clear the line, then **five tie** for four remaining slots. The tiebreak changes *membership*, so the question has no single correct answer set. |
| 3 | Under-determined filter grain | q011 | Reference filters velocity **per store**, then sums stockout **chain-wide** — a mixed grain the question never asks for. |
| 4 | Reference narrower than its question | q015 | Filtered on payment terms *changing*, so a supplier who renegotiated with terms held at 30 was excluded. The question asks who renegotiated. |
| 5 | Grouping distinct entities by name | q035 | `GROUP BY pr.name` merges 46 promotions into 32 names. "Atta, Rice & Dal — 25% off" is three separate campaigns. |
| 6 | Contradicts a published definition | q045, q019 | q045 required `below_reorder_point` when the context defines *about to run out* as cover < 7 (that is *running low*). q019 narrowed a period the question left unstated, when the context says unstated means all history. |
| 7 | Ratio magnitude | q047 | Model returned the share as `0.0501`, reference as `5.0`. "Share" fixes neither. Iteration 5: the references are *consistent* on magnitude (7 of 8 agree with the model) — q047 is the single genuine under-determination, not a reference-set defect. |
| 8 | Row identity — **reframed by item 22**, read them together | q024, q042 | `ST-01` vs `Kothrud`; `festival_id` vs an invented `'Holi 2025'`. **The originally-drafted label fix would have left q042 failing.** |
| 9 | Unstated predicate in reference | q008 | `HAVING sum(units_sold) > 200`, a floor the question never mentions. Inert today (lowest nearby is 1,713) but wrong. |
| 10 | Stale `intent` | q005 | Says `on_hand <= 5`; question and reference say `<= 2`. **Isolated — all 47 `intent` fields were checked and this is the only one.** |

### FREE — scoring contract (`scoring.py`)

| # | defect | questions | what's wrong |
|---|---|---|---|
| 11 | Disambiguation scored on forbidden prose | q003, q018, q027 | Scored on "whether the reply states which reading it took"; `sql_generate.md` line 6 forbids anything but SQL. **Ruled: a reading is read off the predicate.** Implementing this is the whole fix — no prompt change, so the freeze holds. |

### VOIDING — context document (`business_context.md`)

| # | defect | questions | what's wrong |
|---|---|---|---|
| 12 | Context gap | q004 | Does not say whether an explicit cover threshold **replaces** the reorder-point default or **adds** to it, nor whether a reorder question covers lines already at zero. |

### FREE — found by the first prospective predicate trace (2026-08-07)

The trace was run across all 47 references **after** this list was thought
complete. It found defects in references that had already passed diagnosis *and*
the pass audit. Details in `DIAGNOSIS-2026-08-07.md` → *First prospective run*.

| # | defect | questions | fix form | cost |
|---|---|---|---|---|
| 14 | **LIMIT cut falls inside a tie** — the ranking value at position *n* equals *n+1*, so the reference's `sku` tiebreak decides **membership**, not order. **q042: 5 of 10 slots contested among 13 tied.** q008 2 of 10 among 11; q012 4 of 10 among 5; q011 2 of 15 among 5; q039 2 of 15 among 3. | q008, q011, q012, q039, q042 | **`scoring.py`** — accept any valid tie-completion | **FREE** |
| 15 | ~~Stale `traps` tag on q024~~ | — | **RETRACTED — not a defect.** See below. | — |
| 16 | Hardcoded festive window (`2025-09-25`…`2025-10-20`, `/26.0`, `/92.0`) where q024 and q025 read it from the `festivals` table. | q026 | `questions.jsonl` | **FREE** |
| 17 | Intent says "**Ambiguous** between absolute revenue and per-day efficiency", yet scored `ranked_all` against one fixed answer. | q030 | `questions.jsonl` — or re-shape to `disambiguation` | **FREE** |
| 18 | Unstated predicates, **all inert on this data**: q047 `HAVING … FILTER(…) > 0`; q020 not scoped to the named reform; q014 picks `2025-03-15` for "March 2025"; q032 `current_unit_cost IS NOT NULL`. | q047, q020, q014, q032 | `questions.jsonl` | **FREE** |
| 19 | **Ranks on a rounded column** — rounding manufactures ties the data does not contain. Item 1 covers q031 and q047 where it *manifested*; **q033 is latent** (7 distinct values, no collision today). | q033 | `questions.jsonl` | **FREE** |

**Item 14 changes a verdict:** **q039 was recorded as a sound pass and is not.**
It passes only because the model happened to choose the same arbitrary `sku`
tiebreak as the reference.

### Item 14 — why the scoring fix and not the question fix

There are two fix forms with **different costs**, and the choice is real:

| form | what it does | cost |
|---|---|---|
| **Change `scoring.py`** to accept any valid tie-completion | Treats the question as having several correct answer sets, which it does | **FREE** — cached responses re-score |
| Change the **question** to name a tiebreak | "…ties broken by SKU" | **VOIDING for that question** — the model input changes, so its cached response is dead and costs a call |

**Proposed: the scoring fix**, for a reason beyond cost. A question that does not
determine its own tiebreak *genuinely has multiple correct answers*, and writing
a tiebreak into the question authors around the instrument rather than fixing
it — it makes the measurement pass by narrowing what was asked. The scoring fix
states the truth: several answer sets are correct, and the model is not wrong
for picking one.

**If you prefer the question fix**, five questions void and the re-measure grows
by five calls. Still small, but it is a decision, not a default — which is why
this row is stated rather than assumed.

### Item 15 — RETRACTED

The previous revision recorded q024's `traps: ['impossible-yoy']` as a stale tag
contradicting its own intent. **Sweeping `traps` across all 47 disproves that.**
Seven trap tags span different `expects` values, and **every one is a documented
twin pair** — `causal-question` (q036/q047), `pattern-not-people` (q037/q042),
`scope-boundary` (q044/q045), `transactions-are-not-customers` (q038/q043),
`gst-reform-blending` (q018/q019), `stock-zero-vs-low` (q001/q002/q003).

The tag names **the trap being tested**, and both members of a twin carry it.
q024's intent says so outright: *"Counterpart to q023, so the refusal there is a
judgement about the data rather than a blanket refusal to compare festivals."*
The tag is correct.

**It was found incidentally and misread. The class check is what corrected it** —
the same mechanism that turned q012 from one question into five.

### FREE — found by iteration 4's class checks

| # | defect | questions | fix form | cost |
|---|---|---|---|---|
| 21 | **q031 — "worst-margin" fixes neither percentage nor absolute.** The two readings return **disjoint** top-10 sets (STP-* vs DRY-/FNV-/BSK-*, zero overlap). **LATENT, not manifest** — corrected at iteration 5: the model ranked on the margin *ratio*, exactly as the reference does, so neither party diverged and the run was unaffected. The disjointness is a statement about *exposure*, not about severity observed. | q031 | `questions.jsonl` — name the measure | **FREE** |
| 22 | **The reference set is internally inconsistent about naming an entity.** Six references identify a supplier or store by `.name`; **q042 alone uses `.code`**. The model was consistent and was scored wrong only on the outlier. **Supersedes item 8's framing** — the defect is the reference set, not the questions. | q042 (+ q013, q014, q015, q017, q030, q040 as the consistent group) | `questions.jsonl` **or** `scoring.py` | **FREE** either way |

### NOT FIXED — recorded and gated

| # | item | why not |
|---|---|---|
| 20 | `is_active` blind spot | Inert under this seed; all 600 products active. Fixing means changing `random.Random(42)`, which invalidates every expected result set. **Gated to any future seed change** — see `docs/HANDOFF.md`. |

---

## Sequencing

The order is forced by the two costs, and getting it wrong costs a run.

1. **Apply every free item together** — **1–11, 14, 16, 17, 18, 19, 21, 22.**
   (12 is voiding and waits; 13 and 15 are vacant; 20 is gated.) An earlier
   revision of this line said "items 1–11", which predates the trace and would
   have left nine fixes unapplied.
2. **Re-score against the existing cache.** Zero model calls. This yields the
   corrected v2 number for the *same* responses — the cleanest available
   comparison, because the model's answers are held fixed while the instrument
   changes around them.
3. **Then apply item 12** (q004 / `business_context.md`), accepting the void.
4. **Re-measure once** against v2.

> **Do not bundle item 12 with the free batch.** Doing so throws away the free
> re-score at step 2 — the only measurement that isolates instrument change from
> model change — and buys nothing, since the voiding cost is identical either
> way.

---

## What the number is expected to do, and why that is not a result

Of the **10** not-view-covered failures, **8 are instrument** and 2 are model
(q026, q043).

**That figure is a projection and is reported nowhere.** It is what the
arithmetic implies if every diagnosis is right, and it must be *earned* by the
step-2 re-score rather than asserted. It can also move down — the pass audit
found q008 and q005, and a corrected reference can expose a pass that was
passing for the wrong reason.

What is safe to say is only this: **the raw figure measured the instrument at
least as much as the model, in both directions.** That is why it was never acted
on, and why no number is quoted here. The v2 re-measure produces the first
figure this project can stand behind.

---

## Every singleton, checked as a class

The rule is that a defect found once is a candidate class until checked
mechanically. All are now checked, and the result is the argument for the rule:

| singleton | became | note |
|---|---|---|
| q012 — `LIMIT` cut inside a tie | **1 → 5** | q008, q011, q039, q042 all new |
| q031/q047 — ranks on a rounded column | **1 → 3** | q033 new, latent |
| q019 — narrows an unstated period | **1 → 2** | q026 |
| q024/q042 — row identity | **1 → 2 manifest** (12 flagged) | reframed: inconsistent *references*, not under-determined questions |
| q047 — ratio magnitude | **1 → 1** | references consistent; model diverged once |
| q035 — grain conflation | **1 → 1** | |
| q005 — stale `intent` | **1 → 1** | |
| q024 — stale `traps` | **1 → 0** | **retracted** — the convention is universal |

**The prior was uninformative in both directions.** One became five; two stayed
at one; one went to zero and had to be withdrawn. How a defect looked when first
found predicted nothing about what the check would return — which is the case
for checking mechanically rather than judging.

## The decision

1. Declare **instrument v2**; mark the 47×1 as v1 — measured, diagnosed,
   superseded. It keeps its value as the run that found the defects.
2. Replace the fix cap with an **enumerate-then-fix gate**: no fix applied until
   enumeration is complete, then all fixes land in one batch. Keeps the
   expensive-to-guess property that was the cap's real contribution; drops the
   arbitrary number that no longer protects a comparison; scales past ten.
3. ~~Run the predicate-to-words trace across all 47 references.~~ **Done — run
   to stationarity at iteration 5**, which is where items 14–22 came from. It is
   also what retracted item 15 and downgraded item 21. It is
   the new stopping rule and it is now the thing to re-run *after* the batch
   lands, not before.
4. Sequence as above.
