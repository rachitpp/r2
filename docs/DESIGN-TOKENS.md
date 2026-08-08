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

## What this leaves open

- **No dark mode proposed.** A ledger has a paper colour. If you want one it
  should be designed, not derived by inversion.
- **Devanagari** is not in scope — the interface is English — but Public Sans
  has no Devanagari coverage, so if store names ever render in Devanagari this
  needs revisiting rather than falling back silently.
- **The query view** (demo beat 1's answer-beside-SQL) is not wireframed here.
  It is a different surface from the approval card and should be proposed
  separately rather than bundled into a decision about the signature.
