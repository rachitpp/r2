"""The run store. Everything Phase 4 promises is a property of these queries.

ADR-0003 chose to write the loop rather than adopt LangGraph, and the whole of
that bet is here: **the agent is stateless and the database is the source of
truth.** So "survives a server restart" is not something the worker does, it is
something the schema makes unavoidable — a run that was `running` when a process
died is still `running` in the table, still carries its claim, and is reclaimable
by anyone who notices the claim has gone cold.

Three things this module exists to make true rather than to assert:

**Two workers cannot take the same run.** `claim()` uses
`FOR UPDATE SKIP LOCKED`, which is the one correct answer to a Postgres work
queue: `SKIP LOCKED` steps over rows another transaction holds instead of
blocking on them, so N workers drain the queue in parallel and never collide.
`test_runs.py` proves it by claiming concurrently on two connections rather than
by trusting the clause.

**A crash loses nothing.** `reclaim_stale()` returns runs whose claim has gone
cold to `queued`. That is the restart story: no in-memory registry to rebuild, no
checkpointer to restore, just a row whose `claimed_at` stopped moving.

**The audit log falls out of the state.** Every transition writes to
`agent_events` in the SAME transaction as the change it records, so a status and
its explanation cannot disagree — an event written afterwards is an event that
can be missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

#: How long a claim may go without progress before another worker may take it.
#: Generous on purpose: reclaiming a run that is merely slow means running it
#: twice, and a paced model call is slow by design (rule 2's pacer).
STALE_CLAIM = timedelta(minutes=5)

#: How long a drafted proposal stays approvable. A human is in this loop and the
#: prices underneath it move, so the window is short enough that re-validation
#: rarely has to refuse and long enough that a person can read the card.
DEFAULT_EXPIRY = timedelta(hours=1)


@dataclass(frozen=True)
class Run:
    agent_run_id: int
    prompt: str
    requested_by: str
    role: str
    store_id: int | None
    max_tool_calls: int
    tool_calls_used: int
    max_spend_usd: float
    status: str


def record_event(
    cur,
    agent_run_id: int,
    kind: str,
    *,
    detail: dict[str, Any] | None = None,
    actor: str | None = None,
    proposed_action_id: int | None = None,
) -> None:
    """Append to the audit log.

    Takes a CURSOR rather than a connection, deliberately: the event must be
    written inside the same transaction as the change it describes. An event
    written on its own connection is one that can be absent while the state
    change it explains is present, and a log with holes is not a log.
    """
    cur.execute(
        """insert into agent_events
           (agent_run_id, proposed_action_id, kind, detail, actor)
           values (%s, %s, %s, %s, %s)""",
        (agent_run_id, proposed_action_id, kind, json.dumps(detail or {}), actor),
    )


def enqueue(
    conn,
    prompt: str,
    *,
    requested_by: str,
    role: str,
    store_id: int | None,
    max_tool_calls: int = 6,
    max_spend_usd: float = 0.50,
) -> int:
    """Queue a run and return immediately.

    The API never waits for an agent. `POST /runs` writes this row and hands
    back an id; the work happens in a worker. That is what makes a restart
    survivable and what keeps a request handler from holding a connection open
    across a paced model call — the mistake `live.py` already carries a note
    about, where the read-only role's idle timeout makes it visible.

    Rule 5 is enforced by the schema below this — the
    `agent_runs_scoped_role_has_store` constraint — so a store-scoped role with
    no store cannot be queued by any path, not just this one.
    """
    with conn.cursor() as cur:
        cur.execute(
            """insert into agent_runs
               (prompt, requested_by, role, store_id, max_tool_calls, max_spend_usd)
               values (%s, %s, %s, %s, %s, %s)
               returning agent_run_id""",
            (prompt, requested_by, role, store_id, max_tool_calls, max_spend_usd),
        )
        run_id = cur.fetchone()[0]
        record_event(cur, run_id, "run_queued", actor=requested_by)
    conn.commit()
    return run_id


def claim(conn, worker: str) -> Run | None:
    """Take the oldest queued run, or return None.

    `FOR UPDATE SKIP LOCKED` is the whole mechanism. Without `SKIP LOCKED` a
    second worker blocks on the row the first is holding and the queue becomes
    serial; with it, the second steps over and takes the next one. The
    `LIMIT 1` and the `ORDER BY` are inside the locking select so the choice of
    row and the lock on it are the same decision.
    """
    with conn.cursor() as cur:
        cur.execute(
            """update agent_runs
                  set status = 'running',
                      claimed_by = %s,
                      claimed_at = now(),
                      started_at = coalesce(started_at, now())
                where agent_run_id = (
                      select agent_run_id from agent_runs
                       where status = 'queued'
                       order by created_at
                       for update skip locked
                       limit 1
                )
            returning agent_run_id, prompt, requested_by, role, store_id,
                      max_tool_calls, tool_calls_used, max_spend_usd, status""",
            (worker,),
        )
        row = cur.fetchone()
        if row is None:
            conn.commit()
            return None
        record_event(cur, row[0], "run_claimed", detail={"worker": worker})
    conn.commit()
    return Run(
        agent_run_id=row[0],
        prompt=row[1],
        requested_by=row[2],
        role=row[3],
        store_id=row[4],
        max_tool_calls=row[5],
        tool_calls_used=row[6],
        max_spend_usd=float(row[7]),
        status=row[8],
    )


def heartbeat(conn, agent_run_id: int) -> None:
    """Say the claim is still live. Called between tool calls, not on a timer.

    A worker that stops making progress stops heartbeating, which is the signal
    `reclaim_stale` reads. A background timer would keep beating through a hung
    step and defeat the point.
    """
    with conn.cursor() as cur:
        cur.execute(
            "update agent_runs set claimed_at = now() where agent_run_id = %s",
            (agent_run_id,),
        )
    conn.commit()


def reclaim_stale(conn, older_than: timedelta = STALE_CLAIM) -> list[int]:
    """Return runs whose claim has gone cold to `queued`. **This is the restart
    story.**

    Nothing is rebuilt and nothing is restored. A run that was `running` when
    its worker died is still `running` in the table with a `claimed_at` that
    stopped moving, so noticing it is a `WHERE` clause. That is the argument
    ADR-0003 made against adopting a framework checkpointer, expressed as one
    query.

    Logged as `run_queued` with the previous worker recorded, so the audit shows
    a run was taken twice and why rather than silently restarting.
    """
    with conn.cursor() as cur:
        # A CTE, because RETURNING gives the NEW row and this statement nulls
        # `claimed_by` — so `returning claimed_by` reports None and the audit
        # records "reclaimed from nobody". That was the first version, and it
        # lost the one fact the event exists to carry: WHICH worker died.
        # Selecting first keeps the old value; SKIP LOCKED keeps two sweepers
        # from reclaiming the same run.
        cur.execute(
            """with stale as (
                   select agent_run_id, claimed_by
                     from agent_runs
                    where status = 'running'
                      and claimed_at < now() - %s::interval
                      for update skip locked
               ), reclaimed as (
                   update agent_runs a
                      set status = 'queued', claimed_by = null, claimed_at = null
                     from stale s
                    where a.agent_run_id = s.agent_run_id
                returning a.agent_run_id
               )
               select agent_run_id, claimed_by from stale""",
            (older_than,),
        )
        rows = cur.fetchall()
        for run_id, previous in rows:
            record_event(
                cur,
                run_id,
                "run_queued",
                detail={"reclaimed_from": previous, "reason": "claim went stale"},
            )
    conn.commit()
    return [row[0] for row in rows]


def spend(conn, agent_run_id: int, *, calls: int, usd: float) -> None:
    """Record what a tool call cost.

    The ceiling is a CHECK constraint on the table (rule 3), so exceeding it
    raises rather than logging a warning nobody reads. A budget enforced by the
    caller is a budget the caller can forget.
    """
    with conn.cursor() as cur:
        cur.execute(
            """update agent_runs
                  set tool_calls_used = tool_calls_used + %s,
                      spend_usd = spend_usd + %s
                where agent_run_id = %s""",
            (calls, usd, agent_run_id),
        )
        record_event(
            cur, agent_run_id, "tool_called", detail={"calls": calls, "usd": usd}
        )
    conn.commit()


def draft(
    conn,
    agent_run_id: int,
    *,
    tool: str,
    args: dict,
    reasoning: str,
    inputs_used: dict,
    estimated_total: float | None = None,
    spending_cap: float | None = None,
    expires_in: timedelta = DEFAULT_EXPIRY,
) -> int:
    """Draft a proposal. **The agent drafts; it does not place.**

    `inputs_used` is what makes re-validation possible rather than aspirational:
    the facts this was drafted against, each with the value read. Without it,
    "a proposal drafted against a price that has since moved refuses to fire" is
    a sentence with no mechanism behind it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """insert into proposed_actions
               (agent_run_id, tool, args, reasoning, inputs_used,
                estimated_total, spending_cap, expires_at)
               values (%s,%s,%s,%s,%s,%s,%s, now() + %s::interval)
               returning proposed_action_id""",
            (
                agent_run_id,
                tool,
                json.dumps(args),
                reasoning,
                json.dumps(inputs_used),
                estimated_total,
                spending_cap,
                expires_in,
            ),
        )
        proposal_id = cur.fetchone()[0]
        record_event(
            cur,
            agent_run_id,
            "proposal_drafted",
            detail={"tool": tool, "estimated_total": estimated_total},
            proposed_action_id=proposal_id,
        )
        cur.execute(
            """update agent_runs set status = 'awaiting_approval'
                where agent_run_id = %s""",
            (agent_run_id,),
        )
    conn.commit()
    return proposal_id


def finish(conn, agent_run_id: int, *, status: str, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """update agent_runs
                  set status = %s, error = %s, finished_at = now(),
                      claimed_by = null
                where agent_run_id = %s""",
            (status, error, agent_run_id),
        )
        record_event(
            cur,
            agent_run_id,
            "run_failed" if status == "failed" else "run_finished",
            detail={"error": error} if error else {},
        )
    conn.commit()


def expire_due(conn) -> list[int]:
    """Mark proposals whose window has closed.

    Expiry is a column, so this is a sweep rather than a set of timers that
    would not survive a restart. A proposal is expired because the clock says
    so, not because a process was running when it happened.
    """
    with conn.cursor() as cur:
        cur.execute(
            """update proposed_actions
                  set status = 'expired'
                where status = 'pending' and expires_at <= now()
            returning proposed_action_id, agent_run_id""",
            (),
        )
        rows = cur.fetchall()
        for proposal_id, run_id in rows:
            record_event(cur, run_id, "expired", proposed_action_id=proposal_id)
    conn.commit()
    return [row[0] for row in rows]


def _row_to_dict(cur, row: tuple) -> dict:
    """Label a row from the cursor's own description rather than a literal.

    The alternative — a key list written beside the query — has to match the
    SELECT's column order, and adding a column in the middle silently mislabels
    every field after it. Every value present, every value wrong, nothing
    raising.
    """
    return {
        column.name: value for column, value in zip(cur.description, row, strict=True)
    }


def load_run(conn, agent_run_id: int) -> dict | None:
    """The run and everything hanging off it, for `GET /runs/{id}` and the card."""
    with conn.cursor() as cur:
        cur.execute(
            """select agent_run_id, status, prompt, requested_by, role, store_id,
                      max_tool_calls, tool_calls_used, max_spend_usd, spend_usd,
                      created_at, started_at, finished_at, claimed_by, error
                 from agent_runs where agent_run_id = %s""",
            (agent_run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        # Keys from the cursor, not from a literal beside the query. A
        # hardcoded list has to match the SELECT's column ORDER, and when
        # someone adds a column in the middle it silently mislabels every field
        # after it — the values are all present and all wrong.
        run = _row_to_dict(cur, row)

        cur.execute(
            """select proposed_action_id, tool, args, reasoning, inputs_used,
                      status, expires_at, approved_by, approved_at, executed_at,
                      refusal, estimated_total, spending_cap
                 from proposed_actions where agent_run_id = %s
                order by proposed_action_id""",
            (agent_run_id,),
        )
        run["proposals"] = [_row_to_dict(cur, r) for r in cur.fetchall()]

        cur.execute(
            """select kind, detail, actor, occurred_at, proposed_action_id
                 from agent_events where agent_run_id = %s order by agent_event_id""",
            (agent_run_id,),
        )
        run["events"] = [_row_to_dict(cur, r) for r in cur.fetchall()]
    return run


def now() -> datetime:

    return datetime.now(UTC)
