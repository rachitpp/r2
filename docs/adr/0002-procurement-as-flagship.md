# ADR-0002: Procurement agent as flagship, not the anomaly investigator

Date: 2026-08-05
Status: Accepted

## Context

The first design review recommended a loss-prevention / anomaly investigator as
the flagship agentic workflow, on the grounds that open-ended investigation is a
genuine LLM strength with no SQL equivalent, whereas procurement's steps reduce
to sorts and queries. That reasoning was sound in the abstract and is reversed
here by project constraints that were unknown when it was written.

## Decision

**Procurement is the flagship.** Detect low stock → check supplier terms → draft
a purchase order with written reasoning → pause for human approval → on approval,
execute and log.

## Alternative rejected

Anomaly / loss-prevention investigator.

## Why

1. **The real corpus is supplier and policy documents.** Procurement is the
   workflow those documents feed. Anomaly investigation runs on transaction data
   that would have to be fabricated — meaning the project's one genuine data asset
   would sit unused while the demo showed synthetic fraud.
2. **Free tier.** Procurement is a bounded ~5-step workflow. Anomaly investigation
   is open-ended exploration, which is precisely the shape that burns rate limits.
3. **Anomaly is read-only**, so it could be finished without ever building the
   approval queue and audit log — the guardrails that are the point.
4. **Procurement accuses no one.** See below.

## The pattern-not-people constraint

If anomaly detection is built in Phase 6, this is binding:

**The agent reports patterns, never people.** Output reads "SKU 4471 shows 12%
variance between recorded and counted stock over 30 days across 3 shifts" — not
"Cashier <name> has an elevated void rate." Individual-level detail sits behind an
explicit human action that is itself logged, so the system records who went
looking.

This is better ethics and better design at once: statistical correlation over a
small sample generates false accusations at a rate that would be unacceptable
with a real person's job attached, and surfacing a pattern for a human to
investigate is what actual loss-prevention tooling is supposed to do.

Never demo with real employee names, including realistic-looking synthetic ones,
in a public repo.

## What would flip it

Nothing available now. If the corpus turns out to contain no usable supplier terms
— making procurement ungroundable — reconsider, with the constraint above binding
from day one rather than deferred.