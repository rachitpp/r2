"""The worker: claim a run, do it, finish it. Nothing is held in memory.

`POST /runs` returns an id immediately and this process does the work, which is
what makes two separate promises true at once:

  **"survives a server restart"** — kill this process mid-run and the row is
  still `running` with a `claimed_at` that stopped moving. Another worker
  reclaims it. There is no registry to rebuild and no checkpointer to restore,
  which is the whole of ADR-0003's argument against adopting LangGraph.

  **no connection is held across a model call** — `live.py` already carries a
  note about this: the read-only role sets a 10s idle-in-transaction timeout and
  a paced generation takes longer, so Postgres would terminate the connection.
  Correctly. Holding a transaction open across a call to a third party is the
  mistake; the timeout only makes it visible.

**The agent step is a stub and says so at startup.** Phase 4's loop is not
written yet, and a worker that quietly drafted invented proposals into
`proposed_actions` would put rows there that nothing downstream could tell from
real ones — the same guard `corpus_extract.py` has for the same reason. So the
stub refuses unless `--allow-stub` is passed, and every proposal it writes is
labelled in its own reasoning.

Run with `make worker`. No model calls, no key, no quota.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "api" / "src"))

from pos_copilot import runs  # noqa: E402

STUB_MARK = "[STUB] "

_stopping = False


def _stop(signum, frame) -> None:  # pragma: no cover - signal path
    """Finish the run in hand, then exit.

    A worker killed between claiming and finishing is exactly the case
    `reclaim_stale` handles, so a hard exit is survivable — but leaving a run
    claimed when we knew we were going down is rudeness the queue pays for in
    stale-claim latency.
    """
    global _stopping
    _stopping = True
    print("\n  stopping after the current run…")


def stub_step(conn, run: runs.Run) -> None:
    """Stand in for the agent loop. Drafts one clearly-labelled proposal.

    This exists so the PERSISTENCE path can be exercised end to end — claim,
    work, draft, await approval, audit — before a single model call is made.
    Phase 2 learned this the expensive way: every path was stub-driven first and
    the real run then found four defects that were in the plumbing, not the
    model.
    """
    runs.spend(conn, run.agent_run_id, calls=1, usd=0.0)
    runs.heartbeat(conn, run.agent_run_id)
    runs.draft(
        conn,
        run.agent_run_id,
        tool="place_purchase_order",
        args={"supplier_code": "SUP-01", "lines": []},
        reasoning=(
            STUB_MARK
            + "No agent loop exists yet. This proposal was drafted by "
            + "scripts/worker.py --allow-stub to exercise the persistence path, "
            + "and it is not a recommendation about anything."
        ),
        inputs_used={"stub": True},
        estimated_total=0.0,
        spending_cap=25000.0,
        expires_in=timedelta(minutes=30),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--worker-id", default=f"worker-{uuid.uuid4().hex[:8]}")
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument(
        "--once", action="store_true", help="claim at most one run, then exit"
    )
    parser.add_argument(
        "--allow-stub",
        action="store_true",
        help="permit the placeholder agent step to write proposals",
    )
    parser.add_argument("--reclaim-after", type=float, default=300.0)
    args = parser.parse_args(argv)

    if not args.database_url:
        print("DATABASE_URL is not set.")
        return 1
    if not args.allow_stub:
        print("refusing: there is no agent loop yet, and the placeholder step")
        print("would write proposals into proposed_actions that nothing")
        print("downstream could tell apart from real ones. Pass --allow-stub to")
        print("exercise the persistence path deliberately.")
        return 1

    import psycopg

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"worker     {args.worker_id}")
    print("step       STUB — no agent loop yet, no model calls")
    print(f"reclaim    a claim idle for {args.reclaim_after:.0f}s is taken back")
    print()

    conn = psycopg.connect(args.database_url, connect_timeout=30)
    try:
        while not _stopping:
            recovered = runs.reclaim_stale(conn, timedelta(seconds=args.reclaim_after))
            for run_id in recovered:
                print(f"  reclaimed run {run_id} — its worker went away mid-run")

            run = runs.claim(conn, args.worker_id)
            if run is None:
                if args.once:
                    print("  queue empty")
                    return 0
                time.sleep(args.poll)
                continue

            print(f"  claimed run {run.agent_run_id}: {run.prompt[:56]}")
            try:
                stub_step(conn, run)
                print(f"  run {run.agent_run_id} awaiting approval")
            except Exception as exc:
                conn.rollback()
                runs.finish(conn, run.agent_run_id, status="failed", error=str(exc))
                print(f"  run {run.agent_run_id} FAILED: {exc}")

            expired = runs.expire_due(conn)
            for proposal_id in expired:
                print(f"  proposal {proposal_id} expired unapproved")

            if args.once:
                return 0
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
