"""Approve, re-validate, execute — or refuse, which is the interesting one.

`PLAN.md`'s Phase 4 done-condition ends "**and an expired or stale proposal
correctly refuses to fire**". That sentence is the reason `proposed_actions`
carries `inputs_used`: a proposal records the facts it was drafted against, and
execution re-reads them. Without that column the promise has no mechanism behind
it and the honest version would be "we hope nothing moved".

**A refusal here is the system working.** It is written to `proposed_actions.
refusal` and never to `agent_runs.error`, because merging them would make a
guardrail firing look like a fault — and the demo depends on a reader being able
to tell those apart.

**Approval and execution are separate steps on purpose.** A human approves; the
world may still have moved between the click and the write. Executing inside the
approve call would make the check unfalsifiable, since nothing could change in
between.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from .runs import record_event

#: Money is compared to the cent. A supplier price that moved by less than that
#: has not moved; a tolerance any wider starts silently approving real changes.
TOLERANCE = Decimal("0.005")


class NotApprovable(RuntimeError):
    """The proposal is not in a state a human can act on."""


@dataclass(frozen=True)
class Divergence:
    """One recorded input that no longer matches the world."""

    kind: str
    subject: str
    drafted: object
    now: object

    def describe(self) -> str:
        return f"{self.kind} {self.subject}: drafted {self.drafted}, now {self.now}"


def _number(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def revalidate(conn, proposal: dict) -> list[Divergence]:
    """Re-read every recorded input and report what moved.

    Each check names what to look up rather than embedding a query, so a
    proposal cannot smuggle SQL through `inputs_used` — that column is written
    by the agent, and rule 6's principle applies to it as much as to a document:
    **it is data, never instruction.**

    An unknown check kind is a divergence, not a pass. A proposal recording
    something this function cannot verify must not execute on the strength of
    the parts it could.
    """
    checks = (proposal.get("inputs_used") or {}).get("checks") or []
    found: list[Divergence] = []

    with conn.cursor() as cur:
        for check in checks:
            kind = check.get("kind")

            if kind == "supplier_price":
                cur.execute(
                    """select sp.unit_cost
                         from supplier_prices sp
                         join products p using (product_id)
                         join suppliers s using (supplier_id)
                        where s.code = %s and p.sku = %s
                          and sp.valid_period @> current_date""",
                    (check.get("supplier_code"), check.get("sku")),
                )
                row = cur.fetchone()
                current = row[0] if row else None
                drafted = _number(check.get("value"))
                if (
                    current is None
                    or drafted is None
                    or abs(Decimal(str(current)) - drafted) > TOLERANCE
                ):
                    found.append(
                        Divergence(
                            "supplier_price",
                            str(check.get("sku")),
                            check.get("value"),
                            current,
                        )
                    )

            elif kind == "supplier_term":
                cur.execute(
                    """select value_numeric
                         from supplier_term_clauses c
                         join suppliers s using (supplier_id)
                        where s.code = %s and c.clause = %s
                          and c.valid_period @> current_date
                        order by c.effective_from desc limit 1""",
                    (check.get("supplier_code"), check.get("clause")),
                )
                row = cur.fetchone()
                current = row[0] if row else None
                drafted = _number(check.get("value"))
                if (
                    current is None
                    or drafted is None
                    or abs(Decimal(str(current)) - drafted) > TOLERANCE
                ):
                    found.append(
                        Divergence(
                            "supplier_term",
                            str(check.get("clause")),
                            check.get("value"),
                            current,
                        )
                    )

            else:
                # Deliberately a divergence. A proposal carrying a check nobody
                # can verify has not been verified, and treating it as a pass
                # would let an unknown kind become a way through.
                found.append(
                    Divergence("unverifiable", str(kind), check.get("value"), None)
                )

    return found


def approve(conn, proposed_action_id: int, *, approver: str) -> dict:
    """Record a human decision. Does NOT execute.

    Separate from execution so the window between them is real — that window is
    where a price moves, and closing it would make the re-validation check
    impossible to fail.
    """
    with conn.cursor() as cur:
        cur.execute(
            """update proposed_actions
                  set status = 'approved', approved_by = %s, approved_at = now()
                where proposed_action_id = %s
                  and status = 'pending'
                  and expires_at > now()
            returning agent_run_id""",
            (approver, proposed_action_id),
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            raise NotApprovable(
                f"proposal {proposed_action_id} is not pending, or its window "
                "has closed. An expired proposal is not approvable — the point "
                "of the window is that it shuts."
            )
        record_event(
            cur,
            row[0],
            "approved",
            actor=approver,
            proposed_action_id=proposed_action_id,
        )
    conn.commit()
    return {"proposed_action_id": proposed_action_id, "status": "approved"}


def reject(conn, proposed_action_id: int, *, actor: str, reason: str = "") -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """update proposed_actions
                  set status = 'rejected'
                where proposed_action_id = %s and status in ('pending', 'approved')
            returning agent_run_id""",
            (proposed_action_id,),
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            raise NotApprovable(f"proposal {proposed_action_id} is not rejectable")
        record_event(
            cur,
            row[0],
            "rejected",
            actor=actor,
            detail={"reason": reason} if reason else {},
            proposed_action_id=proposed_action_id,
        )
    conn.commit()
    return {"proposed_action_id": proposed_action_id, "status": "rejected"}


def execute(conn, proposed_action_id: int, *, allow_writes: bool = False) -> dict:
    """Re-validate, then execute — or refuse and say exactly what moved.

    **`allow_writes` defaults to False and that is not timidity.** Executing a
    purchase order writes to `purchase_orders`, and three eval reference queries
    read that table without filtering `source`, so the first executed agent row
    silently shifts q017, q040 and q048. Guarding those references costs nothing
    today, because every one of the 16,105 rows is `source = 'seed'` — and it
    becomes a correction the moment this runs for real. Until that guard is in,
    execution is opt-in.
    """
    with conn.cursor() as cur:
        cur.execute(
            """select proposed_action_id, agent_run_id, tool, args, inputs_used,
                      status, expires_at, approved_at, estimated_total, spending_cap
                 from proposed_actions where proposed_action_id = %s""",
            (proposed_action_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise NotApprovable(f"no proposal {proposed_action_id}")
        # Labelled from the cursor, not a literal beside the query — a
        # hardcoded key list has to match the SELECT's column ORDER, and a
        # column added in the middle mislabels every field after it.
        proposal = {
            column.name: value
            for column, value in zip(cur.description, row, strict=True)
        }

    run_id = proposal["agent_run_id"]

    def refuse(why: str) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                """update proposed_actions set status = 'refused', refusal = %s
                    where proposed_action_id = %s""",
                (why, proposed_action_id),
            )
            record_event(
                cur,
                run_id,
                "refused",
                detail={"why": why},
                proposed_action_id=proposed_action_id,
            )
        conn.commit()
        return {"status": "refused", "refusal": why}

    if proposal["status"] != "approved" or proposal["approved_at"] is None:
        raise NotApprovable(
            f"proposal {proposed_action_id} is {proposal['status']}, not approved. "
            "Nothing executes without a human decision first."
        )

    # Expiry is checked here as well as by the sweep, because a proposal can be
    # approved a minute before its window shuts and executed a minute after.
    with conn.cursor() as cur:
        cur.execute("select %s::timestamptz < now()", (proposal["expires_at"],))
        if cur.fetchone()[0]:
            return refuse("the approval window closed before this executed")

    moved = revalidate(conn, proposal)
    if moved:
        return refuse(
            "inputs changed since this was drafted — "
            + "; ".join(d.describe() for d in moved)
        )

    if not allow_writes:
        return refuse(
            "execution is opt-in until the eval reference queries filter "
            "purchase_orders.source, because the first agent row silently moves "
            "q017, q040 and q048"
        )

    with conn.cursor() as cur:
        cur.execute(
            """update proposed_actions set status = 'executed', executed_at = now()
                where proposed_action_id = %s""",
            (proposed_action_id,),
        )
        record_event(
            cur,
            run_id,
            "executed",
            detail={"tool": proposal["tool"]},
            proposed_action_id=proposed_action_id,
        )
        cur.execute(
            """update agent_runs set status = 'done', finished_at = now()
                where agent_run_id = %s""",
            (run_id,),
        )
        record_event(cur, run_id, "run_finished")
    conn.commit()
    return {"status": "executed"}


def as_checks(items: list[dict]) -> str:
    """Build an `inputs_used` payload. One place, so drafters cannot invent a
    shape `revalidate` will silently treat as unverifiable."""
    return json.dumps({"checks": items})
