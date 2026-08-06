# ADR-0003: Own agent loop with state in Postgres, not LangGraph

Date: 2026-08-05
Status: Accepted

## Context

The approval queue is the centerpiece of this project. It requires durable state
across restarts, resumable workflows, approval expiry, idempotency, and
re-validation at execution time.

LangGraph solves exactly this. Verified from LangChain's own changelog (note the
vendor stake): 1.0 reached GA on 22 October 2025, with automatic state
persistence across server restarts, built-in persistence without custom database
logic, explicit framing for multi-day approval processes, and first-class API
support for pausing execution for human review. That is a genuine argument for
adopting it, and it was raised against this decision.

## Decision

Write the loop. Persist state as Postgres rows: `agent_runs` (id, status, plan)
and `proposed_actions` (id, run_id, tool, args, status, expires_at, approved_by).
The agent is stateless; the database is the source of truth.

## Alternative rejected

LangGraph 1.0.

## Why

1. **The framework's value here is a shortcut past work I've already done.** I've
   built an agent loop before. Adopting LangGraph would buy convenience at the
   cost of the most interesting thing in the project being someone else's
   checkpointer.
2. **Free tier makes call budgeting a design constraint**, not an optimisation.
   Explicit control over how many model calls a loop makes is worth more than
   graph abstractions.
3. **DB-rows-as-state is more auditable and more portable** than framework
   session state, and the audit log falls out of it for free.
4. Pydantic AI was also considered. Note for anyone reconsidering: V2 went stable
   on 23 June 2026 and shortened its no-breaking-changes window between majors
   from six months to three — relevant for a project running across months.

## What would flip it

State management in Phase 4 consuming materially more than its ~38h budget. At
that point adopting LangGraph's checkpointer and spending the remaining time on
reasoning quality is the better trade.