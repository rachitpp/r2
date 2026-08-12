"""Assertions for the run store — the persistence Phase 4's promises rest on.

`db`-marked, because these are claims about Postgres behaviour and testing them
against anything else would test the mock. `SKIP LOCKED` in particular cannot be
verified without two real connections racing.

**What each test pins is a sentence the project makes to a reader:**

    "survives a server restart"    test_a_dead_worker_loses_no_work
    "two workers never collide"    test_two_workers_cannot_claim_the_same_run
    "expires"                      test_a_pending_proposal_expires_on_the_clock
    "reasoning visible"            test_the_audit_records_which_worker_died
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from pos_copilot import runs

pytestmark = pytest.mark.db


@pytest.fixture
def clean(conn):
    """Each test gets the queue to itself and leaves nothing behind."""
    with conn.cursor() as cur:
        cur.execute("delete from agent_events")
        cur.execute("delete from proposed_actions")
        cur.execute("delete from agent_runs")
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("delete from agent_events")
        cur.execute("delete from proposed_actions")
        cur.execute("delete from agent_runs")
    conn.commit()


def queue(conn, prompt="draft a PO", role="owner", store_id=None) -> int:
    return runs.enqueue(
        conn, prompt, requested_by="tester", role=role, store_id=store_id
    )


class TestClaiming:
    def test_a_claim_moves_the_run_and_names_the_worker(self, clean):
        run_id = queue(clean)
        claimed = runs.claim(clean, "worker-1")
        assert claimed is not None
        assert claimed.agent_run_id == run_id
        stored = runs.load_run(clean, run_id)
        assert stored["status"] == "running"
        assert stored["claimed_by"] == "worker-1"

    def test_an_empty_queue_returns_none_rather_than_blocking(self, clean):
        assert runs.claim(clean, "worker-1") is None

    def test_two_workers_cannot_claim_the_same_run(self, clean, second_conn):
        """`FOR UPDATE SKIP LOCKED`, proven by racing rather than by reading.

        Without SKIP LOCKED the second worker blocks on the row the first holds
        and the queue goes serial; the failure is a performance cliff, not an
        error, so nothing would report it.
        """
        first, second = queue(clean, "a"), queue(clean, "b")
        a = runs.claim(clean, "worker-A")
        b = runs.claim(second_conn, "worker-B")
        assert a is not None and b is not None
        assert a.agent_run_id != b.agent_run_id
        assert {a.agent_run_id, b.agent_run_id} == {first, second}
        assert runs.claim(clean, "worker-C") is None


class TestRestartSurvival:
    def test_a_dead_worker_loses_no_work(self, clean):
        """THE LOAD-BEARING CLAIM, and ADR-0003's whole argument against
        adopting a framework checkpointer.

        Nothing is rebuilt and nothing is restored: the row is still there with
        a `claimed_at` that stopped moving, so recovery is a WHERE clause.
        """
        run_id = queue(clean)
        runs.claim(clean, "worker-DIES")
        runs.spend(clean, run_id, calls=2, usd=0.02)

        # The process vanishes. Nothing is written to say so — that is the
        # point; a crash does not get to run cleanup code.
        with clean.cursor() as cur:
            cur.execute(
                """update agent_runs set claimed_at = now() - interval '10 minutes'
                    where agent_run_id = %s""",
                (run_id,),
            )
        clean.commit()

        assert runs.reclaim_stale(clean, timedelta(minutes=5)) == [run_id]

        stored = runs.load_run(clean, run_id)
        assert stored["status"] == "queued"
        assert stored["claimed_by"] is None
        # The work already done is still counted, so the rule-3 ceiling is not
        # quietly refunded by a crash.
        assert stored["tool_calls_used"] == 2

        again = runs.claim(clean, "worker-SURVIVES")
        assert again is not None and again.agent_run_id == run_id

    def test_a_live_claim_is_not_stolen(self, clean):
        """Reclaiming a run that is merely slow means running it twice. A paced
        model call is slow by design, so this must not fire on one."""
        queue(clean)
        runs.claim(clean, "worker-BUSY")
        assert runs.reclaim_stale(clean, timedelta(minutes=5)) == []

    def test_a_heartbeat_keeps_a_claim_alive(self, clean):
        run_id = queue(clean)
        runs.claim(clean, "worker-SLOW")
        with clean.cursor() as cur:
            cur.execute(
                """update agent_runs set claimed_at = now() - interval '10 minutes'
                    where agent_run_id = %s""",
                (run_id,),
            )
        clean.commit()
        runs.heartbeat(clean, run_id)
        assert runs.reclaim_stale(clean, timedelta(minutes=5)) == []

    def test_the_audit_records_which_worker_died(self, clean):
        """The first version returned `claimed_by` from the UPDATE that had just
        nulled it, so the audit said "reclaimed from None" — losing the one fact
        the event exists to carry."""
        run_id = queue(clean)
        runs.claim(clean, "worker-GHOST")
        with clean.cursor() as cur:
            cur.execute(
                """update agent_runs set claimed_at = now() - interval '10 minutes'
                    where agent_run_id = %s""",
                (run_id,),
            )
        clean.commit()
        runs.reclaim_stale(clean, timedelta(minutes=5))

        reclaims = [
            event
            for event in runs.load_run(clean, run_id)["events"]
            if event["kind"] == "run_queued" and event["detail"].get("reclaimed_from")
        ]
        assert reclaims, "the reclaim was not recorded at all"
        assert reclaims[-1]["detail"]["reclaimed_from"] == "worker-GHOST"


class TestProposals:
    def test_drafting_moves_the_run_to_awaiting_approval(self, clean):
        run_id = queue(clean)
        runs.claim(clean, "w")
        runs.draft(
            clean,
            run_id,
            tool="place_purchase_order",
            args={"supplier_code": "SUP-01"},
            reasoning="cover is 1.4 days against a 2-day lead time",
            inputs_used={"on_hand": 12},
            estimated_total=18240.0,
            spending_cap=25000.0,
        )
        stored = runs.load_run(clean, run_id)
        assert stored["status"] == "awaiting_approval"
        assert len(stored["proposals"]) == 1
        assert stored["proposals"][0]["status"] == "pending"

    def test_inputs_used_survives_the_round_trip(self, clean):
        """Without these the promise that a proposal re-validates before firing
        has no mechanism behind it — there would be nothing to compare."""
        run_id = queue(clean)
        runs.claim(clean, "w")
        runs.draft(
            clean,
            run_id,
            tool="place_purchase_order",
            args={},
            reasoning="r",
            inputs_used={"unit_cost": 39.25, "read_at": "2026-06-30"},
        )
        proposal = runs.load_run(clean, run_id)["proposals"][0]
        assert proposal["inputs_used"]["unit_cost"] == 39.25

    def test_a_pending_proposal_expires_on_the_clock(self, clean):
        """Expiry is a column, so a sweep finds it. A timer would not survive
        the restart this whole design is built around."""
        run_id = queue(clean)
        runs.claim(clean, "w")
        proposal_id = runs.draft(
            clean,
            run_id,
            tool="t",
            args={},
            reasoning="r",
            inputs_used={},
            expires_in=timedelta(hours=1),
        )
        assert runs.expire_due(clean) == []
        # BOTH dates move. `expires_at > created_at` is a real invariant — a
        # proposal that expired before it was drafted is nonsense — so an aged
        # proposal is one whose creation is also in the past. The first version
        # of this test moved only `expires_at` and was refused by the
        # constraint, correctly.
        with clean.cursor() as cur:
            cur.execute(
                """update proposed_actions
                      set created_at = now() - interval '2 hours',
                          expires_at = now() - interval '1 hour'
                    where proposed_action_id = %s""",
                (proposal_id,),
            )
        clean.commit()
        assert runs.expire_due(clean) == [proposal_id]
        assert runs.load_run(clean, run_id)["proposals"][0]["status"] == "expired"

    def test_expiry_does_not_touch_an_approved_proposal(self, clean):
        """Only `pending` expires. Sweeping an approved-but-unexecuted proposal
        would cancel a decision a human already made."""
        run_id = queue(clean)
        runs.claim(clean, "w")
        proposal_id = runs.draft(
            clean, run_id, tool="t", args={}, reasoning="r", inputs_used={}
        )
        with clean.cursor() as cur:
            cur.execute(
                """update proposed_actions
                      set status = 'approved', approved_by = 'rachit',
                          approved_at = now(),
                          created_at = now() - interval '2 hours',
                          expires_at = now() - interval '1 hour'
                    where proposed_action_id = %s""",
                (proposal_id,),
            )
        clean.commit()
        assert runs.expire_due(clean) == []


class TestScope:
    def test_a_scoped_role_without_a_store_cannot_be_queued(self, clean):
        """Rule 5, below the API. The endpoint refuses too, but this is the
        floor: no path can queue an unscoped clerk."""
        import psycopg

        with pytest.raises(psycopg.errors.CheckViolation):
            queue(clean, role="clerk", store_id=None)
        clean.rollback()

    def test_a_scoped_role_with_a_store_is_fine(self, clean):
        assert queue(clean, role="clerk", store_id=1)
