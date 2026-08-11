"""The live model path: generate the SQL, guard it, run it, show it.

Demo mode answers demo beat 1 from a fixed file (`demo.py`) and that is where
the demo stays. ADR-0001's resolution rests on it: a canned path is
deterministic by construction, so the model's measured cross-run variance
(10.6%) cannot reach a repeated demo. **This module does not replace that path.**
It is the opt-in other half — it spends the reader's own credentials (rule 2),
and it is where the variance lives.

Four things it owes that the demo path does not:

1. **A ceiling.** Rule 2: every runner carries a call ceiling and a spend
   ceiling. An HTTP endpoint that calls a paid model is a runner whose loop is
   held by whoever is holding the browser's refresh key.
2. **Scope in the prompt, before generation** (rule 5). The scope string is the
   measured one — `store_id = 1 (Kothrud, Pune)` — which carries the predicate
   itself rather than describing it, and the store's name is read from the
   database so an unknown store is a 404 rather than a query scoped to nothing.
3. **Refusals kept apart from failures.** `-- INSUFFICIENT SCHEMA` and
   `-- OUT OF SCOPE` are the model answering honestly. A guard rejection or a
   Postgres error is the model getting it wrong. Folding those into one field
   would repeat, one layer out, the mistake `prompts/README.md` forbids for the
   two sentinels themselves.
4. **No response cache.** The eval caches on (prompt fingerprint, question id,
   run index) so re-scoring is free. Caching here would make this path look
   steadier than the measurement says it is — and the measurement is the
   argument that keeps generated SQL at all.

Refusal classification imports `scoring.refusal_kind` rather than re-deriving
it. A live path that recognised refusals by different rules than the instrument
would make the published number describe something other than the product.

**Known limit, stated rather than papered over:** for a scoped role this relies
on the model putting the predicate in the query it writes. `check_scope` is a
tripwire behind that, not the mechanism, and it can only fire when `store_id` is
among the result columns. Asserting the predicate's presence by pattern-matching
the generated SQL is the regexes-guessing-at-SQL-structure defect that
`docs/HANDOFF.md` records as instance eight, so it is deliberately not done. The
real fix is a per-store database role, and that is not Phase 1.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import psycopg

from pos_copilot import env
from pos_copilot.model import Budget, Provider, resolve_provider
from pos_copilot.prompts import load_sql_prompt
from pos_copilot.readonly_sql import (
    UNSCOPED_ROLES,
    UnsafeQuery,
    execute,
    guard,
    visible_stores,
)
from pos_copilot.scoring import refusal_kind, strip_fences

#: A connection factory, not a connection. Two short-lived connections are
#: opened per live request and neither is held across the model call — see
#: `answer`.
Connect = Callable[[], Any]


class UnknownStore(LookupError):
    """The request named a store that is not in the database."""


@dataclass(frozen=True)
class LiveResult:
    """One live answer, with the failure kinds kept apart.

    Exactly one of `refusal`, `error` and `result` is set. `generated_sql` is
    what the model wrote, and it is present whenever the model wrote SQL —
    including when that SQL was refused or failed, because a query you cannot
    see is a query you cannot check.
    """

    generated_sql: str | None = None
    refusal: str | None = None
    error: str | None = None
    result: dict | None = None


def as_of_date() -> str:
    """What this system means by "today" — never wall-clock.

    The seed has a fixed end date, so `current_date` is not today here and SQL
    using it silently returns nothing. `.env.example` carries the value, and a
    blank one falls back rather than sending the model `Today's date is .`
    """
    return env.text("AS_OF_DATE", "2026-06-30")


@lru_cache(maxsize=1)
def budget() -> Budget:
    """The process-wide ceiling, per rule 2.

    Process-wide rather than per-request on purpose: a per-request budget is a
    ceiling of one call, which is not a ceiling. The defaults are sized for a
    demo sitting — the 47x3 measurement cost ~$0.02 a call, so 50 calls is
    about a dollar — and raising them is an env change someone makes on purpose.
    """
    return Budget(
        max_calls=env.integer("LIVE_MAX_CALLS", 50),
        max_spend_usd=env.number("LIVE_MAX_SPEND_USD", 1.00),
    )


@lru_cache(maxsize=1)
def provider() -> Provider:
    """One provider for the process, so the pacer's memory survives requests.

    Building one per request would hand every request a fresh `Pacer` with no
    record of the last call, and the RPM floor the pacer exists to hold would
    stop existing at exactly the moment two people used it.
    """
    return resolve_provider("PLAN")


def readiness() -> dict:
    """Whether the live path could serve, without making a model call.

    `/health` reporting `ok` while the only endpoint 503s on every request is
    this project's recurring defect class — a check that is not running wearing
    the label of one that is. Resolving the provider reads env and a local
    credential file; it opens no socket.
    """
    try:
        p = provider()
    except RuntimeError as exc:
        return {"status": "unconfigured", "detail": str(exc)}
    return {"status": "ok", "provider": p.name, "model": p.model}


#: The model call is serialised. `model.py` is serial by design — "RPM is the
#: first ceiling on a free tier" — and neither `Pacer` nor `Budget` is
#: thread-safe, while FastAPI runs sync handlers in a threadpool. Two
#: concurrent askers queue, which is the correct behaviour for a rate-limited
#: endpoint and keeps both the ceiling and the pacing honest.
_generate_lock = threading.Lock()


def generate(question: str, role: str, store_scope: str) -> str:
    """Render the prompt from files (ADR-0008) and return the model's SQL."""
    prompt = load_sql_prompt().render(
        question=question,
        as_of_date=as_of_date(),
        user_role=role,
        store_scope=store_scope,
    )
    with _generate_lock:
        ceiling = budget()
        ceiling.check(prompt)
        sql = provider().generate(prompt)
        ceiling.record(prompt)
    return strip_fences(sql)


def scope_label(connect: Connect, role: str, store_id: int | None) -> str:
    """The `{store_scope}` string, in the shape the prompt was measured with.

    `prompts/README.md` documents it as `store_id = 3 (Dharampeth, Nagpur)` and
    the 47x3 run used exactly that, predicate included. Phrasing it differently
    here would make this path's behaviour something the measurement does not
    describe.

    The name comes from the database rather than a table in this file, so a
    store that does not exist is `UnknownStore` instead of a query scoped to
    nobody. No connection is opened for an unscoped role.
    """
    if role in UNSCOPED_ROLES:
        return "all stores"
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name, city FROM stores WHERE store_id = %s", (store_id,))
        row = cur.fetchone()
    if row is None:
        raise UnknownStore(
            f"no store with store_id = {store_id}. The scope would have "
            "matched nothing, which is not the same as chain-wide."
        )
    return f"store_id = {store_id} ({row[0]}, {row[1]})"


def answer(
    question: str,
    role: str,
    store_id: int | None,
    max_rows: int,
    connect: Connect,
) -> LiveResult:
    """Question in; answer, refusal or failure out — with the SQL either way."""
    # Rule 5: both of these run before a prompt exists, so a scoped request
    # that cannot be scoped never reaches the model at all.
    visible = visible_stores(role, store_id)
    scope = scope_label(connect, role, store_id)

    # Nothing is held open across the model call. The read-only role sets
    # idle_in_transaction_session_timeout = 10s and a paced generation takes
    # longer than that, so Postgres would terminate the connection — correctly.
    # Holding a transaction open across a call to a third party is the mistake;
    # the timeout only makes it visible. `api/scripts/eval_sql.py` carries the
    # same note for the same reason.
    sql = generate(question, role, scope)

    if refusal_kind(sql) is not None:
        # The model declining, not the model failing. No query ran, and the
        # sentinel is returned verbatim — the caller decides how to say it.
        return LiveResult(refusal=sql.strip())

    # Guarded before connecting, so a query that will be refused does not open a
    # database connection first. Any other leading comment is left to the guard,
    # which strips comments and judges the SQL, rather than to a leading-`--`
    # heuristic. `execute` guards again — the check is cheap and deterministic,
    # and it stays the single point of enforcement (rule 4) rather than becoming
    # something this function is trusted to have done.
    try:
        guard(sql, max_rows)
        with connect() as conn:
            result = execute(conn, sql, max_rows=max_rows, visible_store_ids=visible)
    except UnsafeQuery as exc:
        return LiveResult(
            generated_sql=sql,
            error=f"the generated query was refused before execution: {exc}",
        )
    except psycopg.Error as exc:
        # Wrong-and-obvious, which `sql_generate.md` prefers to
        # wrong-and-plausible. Reported as a failure of the generated query,
        # not as a server fault, and the query is shown so it can be read.
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        return LiveResult(
            generated_sql=sql,
            error=f"the generated query failed to execute: "
            f"{type(exc).__name__}: {detail}",
        )

    return LiveResult(generated_sql=sql, result=result)
