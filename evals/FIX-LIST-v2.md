# Fix list for the instrument v2 sitting

**Decision artifact. Nothing here is applied.** Complete as of 2026-08-07:
47 questions diagnosed, all 30 passes audited, all 47 `intent` fields checked,
and the predicate trace run to stationarity over **four** iterations — every
known singleton has now been checked as a class.

Reasoning for each item is in `evals/DIAGNOSIS-2026-08-07.md`. This page exists
so the decision can be taken without re-reading it.

---

## The run is void by enumeration, not by budget

The fix cap was 10 per round, with 1 spent. Enumeration completed the list and
**pushed it past the cap on its own** — the pass audit added q008, q005's stale
`intent`, and the `is_active` blind spot to a list already at 10 with one spare.

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
| 1 | Ordering by a rounded column | q031, q047 | `round(…,1)` manufactures a tie the data does not contain, then `sku` breaks it — inverting the true order. STP-0028 (12.0368%) is genuinely worse than STP-0007 (12.0467%). |
| 2 | LIMIT boundary inside a tie | q012 | Six products clear the line, then **five tie** for four remaining slots. The tiebreak changes *membership*, so the question has no single correct answer set. |
| 3 | Under-determined filter grain | q011 | Reference filters velocity **per store**, then sums stockout **chain-wide** — a mixed grain the question never asks for. |
| 4 | Reference narrower than its question | q015 | Filtered on payment terms *changing*, so a supplier who renegotiated with terms held at 30 was excluded. The question asks who renegotiated. |
| 5 | Grouping distinct entities by name | q035 | `GROUP BY pr.name` merges 46 promotions into 32 names. "Atta, Rice & Dal — 25% off" is three separate campaigns. |
| 6 | Contradicts a published definition | q045, q019 | q045 required `below_reorder_point` when the context defines *about to run out* as cover < 7 (that is *running low*). q019 narrowed a period the question left unstated, when the context says unstated means all history. |
| 7 | Ratio magnitude | q047 | Model returned the share as `0.0501`, reference as `5.0`. "Share" fixes neither. |
| 8 | Row identity | q024, q042 | `ST-01` vs `Kothrud`; `festival_id` vs an invented `'Holi 2025'`. **The originally-drafted label fix would have left q042 failing.** |
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

### NOT FIXED — recorded and gated

| # | item | why not |
|---|---|---|
| 21 | **q031 — "worst-margin" fixes neither percentage nor absolute.** The two readings return **disjoint** top-10 sets (STP-* vs DRY-/FNV-/BSK-*, zero overlap). **LATENT, not manifest** — corrected at iteration 5: the model ranked on the margin *ratio*, exactly as the reference does, so neither party diverged and the run was unaffected. Severe only if a model ever reads it the other way. | q031 | `questions.jsonl` — name the measure | **FREE** |
| 22 | **The reference set is internally inconsistent about naming an entity.** Six references identify a supplier or store by `.name`; **q042 alone uses `.code`**. The model consistently used `.name` and was scored wrong only on the outlier. Fixing q042 to match its siblings is the smaller change; the alternative is accepting either identifier in `scoring.py`. | q042 (+ q030, q013, q014, q015, q017, q040 as the consistent group) | `questions.jsonl` **or** `scoring.py` | **FREE** either way |

### NOT FIXED — recorded and gated (continued)

| # | item | why not |
|---|---|---|
| 20 | `is_active` blind spot | Inert under this seed; all 600 products active. Fixing means changing `random.Random(42)`, which invalidates every expected result set. **Gated to any future seed change** — see `docs/HANDOFF.md`. |

---

## Sequencing

The order is forced by the two costs, and getting it wrong costs a run.

1. **Apply items 1–11 together** (references + scoring contract). All free.
2. **Re-score against the existing cache.** Zero model calls. This yields the
   corrected v2 number for the *same* responses — the cleanest available
   comparison, because the model's answers are held fixed while the instrument
   changes around them.
3. **Then apply item 12** (q004 / `business_context.md`), accepting the void.
4. **Re-measure once** against v2.

> **Do not bundle item 12 with items 1–11.** Doing so throws away the free
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
3. Run the **predicate-to-words trace** across all 47 references. It is the new
   stopping rule and **has not yet been run prospectively against anything**.
4. Sequence as above.
