# Fix list for the instrument v2 sitting

**Decision artifact. Nothing here is applied.** Complete as of 2026-08-07:
47 questions diagnosed, all 30 passes audited, all 47 `intent` fields checked.

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

**Only one item is voiding.** Everything else re-scores free.

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

### NOT FIXED — recorded and gated

| # | item | why not |
|---|---|---|
| 13 | `is_active` blind spot | Inert under this seed; all 600 products active. Fixing means changing `random.Random(42)`, which invalidates every expected result set. **Gated to any future seed change** — see `docs/HANDOFF.md`. |

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
(q026, q043). Correcting them moves not-view-covered from 23/33 to **31/33**.

**That figure is a projection and is reported nowhere.** It is what the
arithmetic implies if every diagnosis is right, and it must be *earned* by the
step-2 re-score rather than asserted. It can also move down — the pass audit
found q008 and q005, and a corrected reference can expose a pass that was
passing for the wrong reason.

What is safe to say: **the raw 69.7% measured the instrument at least as much as
the model.** That is why it was never acted on.

---

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
