# Design plan — PROPOSED, not agreed

**Nothing here is implemented and no component has been written.** CONVENTIONS →
Frontend requires a design plan to be *proposed and agreed* before any UI, and
CLAUDE.md rule 12 says the same. This is the proposal half. Reject, amend, or
take pieces.

It is written down rather than discussed live for one specific reason: the
decision was at risk of being made with whatever attention was left over after
the instrument v2 sitting. Reacting to something concrete is a lighter task than
generating from nothing while depleted.

---

## Concept

> **A ledger you can argue with.**

The audit log is the spine of the interface and reads like a bound ledger. The
approval card is a **docket laid on top of it** — a slip that is not yet part of
the record, awaiting a decision that will commit it.

That is the product's actual argument made visual: the machine drafts, the
record is permanent, and the human is the thing in between. It also matches the
domain honestly — Indian retail runs on the ledger book — without reaching for
marigold-and-saffron pastiche.

---

## Colour

Six named values for `tailwind.config.ts`. **Contrast computed, not asserted**
(WCAG 2.1 relative luminance):

| token | hex | on `paper` | role |
|---|---|---|---|
| `ink` | `#17233A` | **13.85:1** AAA | Body text, display type. Blue-black, the colour of ledger ink |
| `paper` | `#EEF1F4` | — | Page ground. **Cool**, not cream |
| `card` | `#F7F9FA` | 1.07:1 vs paper | The docket. Barely lifted — it is a slip on the ledger, not a modal |
| `indigo` | `#35508C` | **6.92:1** AA | The decisive action. Approve, links, focus ring |
| `brass` | `#7A5A12` | **5.62:1** AA | Awaiting decision. Expiry countdown, draft state |
| `oxide` | `#9C3B2E` | **6.02:1** AA | Stale input, expired, rejected |
| `rule` | `#C2CCD6` | 1.44:1 | Ledger rules and borders. **Decorative only** |

**`rule` must never be the only carrier of meaning** — at 1.44:1 it is invisible
to a good number of readers. Structure it supports; state it never signals.

Indigo is not decoration. It was India's great export dye, it is what ledger ink
actually looks like, and it reads as considered rather than alarming — which is
the right register for a button that spends money.

### Against the three looks to avoid

| the tell | why this is not it |
|---|---|
| Warm cream + high-contrast serif + terracotta | The ground is **cool** (`#EEF1F4`), the display face is a **grotesque, not a serif**, and the warm tones are confined to *status* (`brass`, `oxide`) — never to the surface treatment |
| Near-black + one acid accent | No acid. `ink` is blue-black at 13.85:1 and the accent is a mid-value indigo doing structural work, not glowing against a void |
| Broadsheet hairlines + zero radius | Rules are **ledger rules** — horizontal, structural, carrying rows — not decorative hairlines everywhere. Radius is `4px`: small, deliberate, non-zero |

---

## Type

| role | face | why |
|---|---|---|
| Display | **Bricolage Grotesque** | Genuinely characterful — irregular widths, slightly wrong in a way that reads as made rather than generated. Variable, open-source. **Used only for card headers and section heads**, never for body |
| Body | **Public Sans** | Quiet, highly legible, and not the default-tell that Inter has become |
| Utility | **IBM Plex Mono** | Tabular numerals for money, and it is what SQL should look like. **This project's signature move is showing the query** — the mono face is load-bearing, not ornament |

### Scale

Deliberate, not a ratio applied blindly:

```
display-lg   28 / 1.15   600    card header, page title
display-sm   20 / 1.20   600    section heads
body         15 / 1.55   400    prose, the agent's reasoning
body-sm      13 / 1.50   400    secondary, captions
mono         13 / 1.40   400    figures, SQL, audit rows, countdown  [tnum]
mono-lg      15 / 1.35   500    the money figure on the card
```

Two weights per face. No 300, no 800 — a weight range wider than the interface
needs is itself a tell.

---

## Layout

### Approval card — the signature

```
┌───────────────────────────────────────────────────────────────┐
│ DRAFT · PO-0148                          expires in 41:12  ⏱ │  brass
│ Gokul Dairy Distributors                                      │  display-lg
│ ₹18,240 · 12 lines                                            │  mono-lg
├───────────────────────────────────────────────────────────────┤
│ Why this order                                                │  display-sm
│   Kothrud is below reorder point on 12 dairy lines. Cover     │
│   is 1.4 days against a 2-day contracted lead time, so a      │  body
│   Monday delivery needs this placed today.                    │
│                                                               │
│ Checked against                                               │  display-sm
│   stock as of        2026-06-30 18:04                         │
│   supplier terms     net 30 · min order ₹15,000 · in force    │  mono
│   spending cap       ₹18,240 of ₹25,000                       │
│                                                               │
│ ⚠ Chitale Wadi Toned Milk rose ₹2.50 since this was drafted.  │  oxide
│   It will re-validate before it executes.                     │
├───────────────────────────────────────────────────────────────┤
│   [ Approve order ]   [ Reject ]        view the 12 lines →   │
└───────────────────────────────────────────────────────────────┘
```

Everything the convention asks for is on the face of it: the reasoning, the
inputs, the cap it checked against, a live countdown, and the stale-input
warning. **The evidence is the design.** A card that showed only "PO-0148 —
₹18,240 — Approve?" would be asking for a signature on an argument it hid.

The countdown is `brass` and ticks. Under 5 minutes it goes `oxide`. When a
stale input is detected the whole card gains an `oxide` left border — **state is
carried by border and label together, never by colour alone.**

### Audit log — the spine

```
 DATE     ENTRY                                      BY       AMOUNT
 ──────────────────────────────────────────────────────────────────
 30 Jun   Approved   PO-0148   Gokul Dairy           you     ₹18,240
 30 Jun   Drafted    PO-0148   12 lines below ROP    agent         —
 29 Jun   Expired    PO-0147   Nilgiri Beverage      —             —
 29 Jun   Rejected   PO-0146   over spending cap     you           —
 29 Jun   Approved   PO-0145   Sahyadri Agro         you      ₹9,120
```

Ruled rows, tabular numerals, right-aligned money. **An action keeps its name
through the whole flow** — the button says *Approve order*, the state says
*Approved*, the ledger line says *Approved*. No row is ever edited or removed;
that is what makes it a ledger rather than a list.

---

---

# The query view — the surface that exists today

Proposed separately from the signature above, because bundling them would get
this decided as a side effect of a decision about the approval card. Same
tokens, same type. **It shares nothing else, and specifically it does not
compete** — the convention says spend boldness in one place, and that place is
the approval card. This surface is quiet on purpose.

It is also the only surface backed by working code: `POST /query` returns
exactly the fields wireframed here.

## Its one argument

> **The answer and its derivation are peers, shown together.**

Not an answer with a "show SQL" disclosure — that makes the query a debug
affordance and quietly concedes that the answer is the product. The whole claim
of this project is that an unchecked confident answer is the failure that
matters. So the query sits **beside** the answer at the same visual weight, and
it is never behind a click.

## Answer state

```
┌────────────────────────────────────────────────────────────────────┐
│  Ask about the shop                                    demo mode   │  body-sm, brass
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ What's about to run out at our store this week?           ▾  │  │  body
│  └──────────────────────────────────────────────────────────────┘  │
│  at ( Kothrud ▾ )                                    [ Ask ]       │  indigo
└────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────┬─────────────────────────────────┐
│ ANSWER                           │ THE QUERY THAT PRODUCED IT      │  display-sm
│ 91 rows                          │                                 │  ink, mono
│ ──────────────────────────────── │ SELECT * FROM (                 │
│ SKU       PRODUCT        COVER   │   SELECT sku, product_name,     │  mono, tnum
│ RTC-0001  Soup Mix        1.1    │          on_hand, days_of_cover │
│ BEV-0028  Mango Drink     1.1    │   FROM v_stock_status           │
│ OIL-0003  Cow Ghee        1.2    │   WHERE store_id = 1            │
│ …                                │     AND on_hand > 0             │
│                                  │ ) AS _guarded LIMIT 101         │
└──────────────────────────────────┴─────────────────────────────────┘
```

**Truncated, which is the state that matters** — same row, `brass`, verbatim
from the API rather than a phrasing invented here:

```
│ 91 rows matched; showing the first 3.                              │  brass
```

**That count row is always present and is the same row in both states.** Complete
answers show `91 rows` in `ink`, because a complete answer needs no attention.
Truncated answers show the API's `notice` in `brass`. It never disappears and it
never moves, so a reader learns one place to look — and the difference between
"all of it" and "some of it" is a colour and a sentence in a row they are already
reading.

**It sits at the top of the table, not the bottom.** Silent truncation is the
exact production failure this project is built around: an answer that quietly
shows 100 of 440 rows and says nothing. A footer would reproduce that failure
with extra steps.

> **Both strings above were taken from a running server, not composed.** The
> first draft of this wireframe read `76 rows matched · showing 100`, which is
> not a state the system can produce — matching 76 and showing 100 is not
> truncation — and it invented a separator the API does not emit. It also left
> the far more common untruncated case unspecified, so a builder would have had
> to guess what that row shows when `notice` is `null`. Three defects in one
> illustrative line, none of them visible without running the thing.

The `store_id = 1` predicate is visible in the query on purpose. Rule 5 says
scope belongs in the query rather than applied to results afterwards, and this
is where a reader can see that it was.

## Refusal state — and it is not an error

```
┌────────────────────────────────────────────────────────────────────┐
│  How many customers do we have?                                    │
├────────────────────────────────────────────────────────────────────┤
│  This can't be answered from the data.                             │  display-sm, ink
│                                                                    │
│  This POS records anonymous transactions. There is no customer     │  body
│  table, so a customer count is not something the data can answer.  │
│  Baskets and transactions can be counted; people cannot.           │
│                                                                    │
│  ─────────────  no query was run  ─────────────                    │  rule + body-sm
└────────────────────────────────────────────────────────────────────┘
```

**Refusals render in `ink`, never `oxide`.** A refusal is a *correct answer of a
different kind* — the system declining to fabricate — and styling it red would
teach a reader it is a malfunction to be worked around. `oxide` is reserved for
things that actually went wrong: stale inputs, expiry, rejection.

**"no query was run" is not a placeholder.** The surface promises you always see
what executed; when nothing did, saying so keeps the promise rather than
silently dropping the panel.

## Offering rather than accepting anything

Demo mode answers a fixed set, so the question field is a **combobox over
`GET /demo/questions`**, not a free-text box that 404s on most input. That
endpoint now returns `requires_store` and `expect` for each question, so:

- `requires_store: true` → the store selector enables; **it is never
  pre-filled**, because the API refuses to guess a store rather than answer the
  wrong shop, and a UI that defaults to Kothrud reintroduces exactly that
- `expect: "refusal"` → listed with a quiet **"will decline"** marker, so the
  refusal is *offered as a demonstration* rather than stumbled into

```
  ┌──────────────────────────────────────────────────────────────┐
  │ What's about to run out at our store this week?    needs store│
  │ What was our revenue last month?                              │
  │ What effective tax rate … before and after the GST reform?    │
  │ What were our top 10 products by units last month?            │
  │ How many customers do we have?                    will decline│  brass
  └──────────────────────────────────────────────────────────────┘
```

## Responsive

Two columns become one below `768px`: **answer first, query directly below it,
always expanded.** Collapsing the query behind a disclosure on small screens
would contradict the surface's only argument at precisely the moment a reader is
most likely to skim. It scrolls horizontally inside its own container; the page
never does.

---

## What this leaves open

- **No dark mode proposed.** A ledger has a paper colour. If you want one it
  should be designed, not derived by inversion.
- **Devanagari** is not in scope — the interface is English — but Public Sans
  has no Devanagari coverage, so if store names ever render in Devanagari this
  needs revisiting rather than falling back silently.
- **The live-mode query view is not designed.** When the model generates SQL
  there is a latency to fill and a failure mode — a refused or unsafe query —
  that demo mode cannot produce. That surface should be proposed when the live
  path is built, which is after the q004 fix.
- **No empty state for the audit log** and no zero-results state for a query
  that legitimately matches nothing. Both need writing as copy, not styling —
  the convention is explicit that empty states are an invitation to act.
