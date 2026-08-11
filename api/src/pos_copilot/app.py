"""The query API — demo beat 1.

A question goes in; the answer comes back **beside the SQL that produced it**.
Showing the query is not a debug affordance, it is the product: an answer whose
derivation is invisible cannot be checked, and this project's whole argument is
that unchecked confident answers are the failure that matters.

Scope, per CLAUDE.md rule 5, is applied **before** generation — a clerk's store
is substituted into the query — and `check_scope` runs afterwards only as a
tripwire that refuses rather than filters.

Demo mode is the default and needs no key (rule 2). `DEMO_MODE=false` opts into
the live model path in `live.py`, which spends the reader's own credentials —
and does not replace the canned path, because ADR-0001's resolution rests on
that path staying deterministic.

This module is transport: it maps requests onto `demo` or `live` and maps their
failures onto status codes. The judgement lives in those two.
"""

from __future__ import annotations

from typing import Literal

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pos_copilot import demo, env, live
from pos_copilot.model import BudgetExceeded, RateLimited
from pos_copilot.readonly_sql import (
    DEFAULT_MAX_ROWS,
    ScopeViolation,
    StoreRequired,
    UnsafeQuery,
    execute,
    visible_stores,
)

app = FastAPI(
    title="POS Copilot",
    description="Ask about the shop in English; get the answer and the SQL.",
    version="0.1.0",
)


def readonly_url() -> str:
    url = env.text("READONLY_DATABASE_URL")
    if not url:
        raise HTTPException(500, "READONLY_DATABASE_URL is not set")
    return url


def demo_mode() -> bool:
    return env.text("DEMO_MODE", "true").lower() not in ("false", "0")


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    role: Literal["clerk", "manager", "owner"] = "owner"
    store_id: int | None = Field(default=None, ge=1)
    max_rows: int = Field(default=DEFAULT_MAX_ROWS, ge=1, le=1000)


class Answer(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    total_row_count: int
    truncated: bool
    notice: str | None


class DemoQuestion(BaseModel):
    question: str
    #: True when the question is about one store. The caller must supply
    #: `store_id`; demo mode will not pick one, because picking would answer the
    #: wrong shop without saying so.
    requires_store: bool
    #: "answer" or "refusal". Exposed so a UI can OFFER the refusal as a
    #: demonstration rather than leave a reader to stumble into it.
    expect: Literal["answer", "refusal"]


class QueryResponse(BaseModel):
    mode: Literal["demo", "live"]
    question: str
    #: The SQL actually executed, wrapper and all. Shown, never hidden.
    sql: str | None
    #: What the model wrote, before the guard's wrapper — live mode only, since
    #: demo mode generates nothing. Kept separate from `sql` so `sql` never
    #: stops meaning "what actually ran", and present even when the query was
    #: refused or failed: a query you cannot see is a query you cannot check.
    generated_sql: str | None = None
    #: The model declining, which is a correct answer of a different kind.
    refusal: str | None
    #: The pipeline failing *after* generation — the guard refused the query, or
    #: Postgres rejected it. Never merged with `refusal`: "the data cannot
    #: answer this" and "the model wrote a bad query" are different facts, and
    #: `prompts/README.md` forbids that merge one layer in.
    error: str | None = None
    answer: Answer | None


@app.get("/health")
def health() -> dict:
    """In live mode, report whether the path could actually serve.

    Answering `ok` while every query 503s for want of a credential would be a
    check that is not running wearing the label of one that is. No model call is
    made — `readiness` resolves config and opens no socket.
    """
    if demo_mode():
        return {"status": "ok", "mode": "demo"}
    return {**live.readiness(), "mode": "live"}


@app.get("/demo/questions", response_model=list[DemoQuestion])
def demo_questions() -> list[dict]:
    """What demo mode can answer, what each needs, and what each will do.

    A bare list of strings would force the caller to infer which questions are
    store-scoped, and an inferring caller guesses and defaults — the failure
    `DemoPair.resolve` exists to prevent, one layer up.
    """
    return demo.catalogue()


def _answer_of(result: dict) -> Answer:
    return Answer(
        columns=result["columns"],
        rows=result["rows"],
        row_count=result["row_count"],
        total_row_count=result["total_row_count"],
        truncated=result["truncated"],
        notice=result["notice"],
    )


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    return _demo_answer(request) if demo_mode() else _live_answer(request)


def _demo_answer(request: QueryRequest) -> QueryResponse:
    # Scope is decided here, before any SQL exists.
    try:
        visible = visible_stores(request.role, request.store_id)
    except StoreRequired as exc:
        raise HTTPException(422, str(exc)) from None

    try:
        pair = demo.lookup(request.question)
    except demo.DemoUnavailable as exc:
        raise HTTPException(404, str(exc)) from None

    if pair.sql is None:
        return QueryResponse(
            mode="demo",
            question=request.question,
            sql=None,
            refusal=pair.refusal,
            answer=None,
        )

    try:
        sql = pair.resolve(request.store_id)
    except demo.DemoUnavailable as exc:
        raise HTTPException(422, str(exc)) from None

    try:
        with psycopg.connect(readonly_url()) as conn:
            result = execute(
                conn, sql, max_rows=request.max_rows, visible_store_ids=visible
            )
    except UnsafeQuery as exc:
        raise HTTPException(400, f"query refused before execution: {exc}") from None
    except ScopeViolation as exc:
        # Rule 5: this is a bug being caught, not a filter being applied. It
        # means the query was missing its scope predicate, so it is a 500 —
        # our defect, not the caller's.
        raise HTTPException(500, f"scope tripwire fired: {exc}") from None
    except psycopg.Error as exc:
        raise HTTPException(500, f"database error: {type(exc).__name__}") from None

    return QueryResponse(
        mode="demo",
        question=request.question,
        sql=result["executed_sql"],
        refusal=None,
        answer=_answer_of(result),
    )


def _live_answer(request: QueryRequest) -> QueryResponse:
    """Map the live path's outcomes onto status codes.

    A refused or failed *generated query* is a 200 carrying `error`, not a 4xx:
    the request was well-formed and the system did exactly what it should —
    refuse it and show it. The 4xx and 5xx below are cases where no answer of
    any kind exists.
    """
    try:
        outcome = live.answer(
            question=request.question,
            role=request.role,
            store_id=request.store_id,
            max_rows=request.max_rows,
            connect=lambda: psycopg.connect(readonly_url()),
        )
    except StoreRequired as exc:
        raise HTTPException(422, str(exc)) from None
    except live.UnknownStore as exc:
        raise HTTPException(404, str(exc)) from None
    # The next three are RuntimeError subclasses, so they must be caught above
    # it — ordering here is load-bearing, not stylistic.
    except RateLimited as exc:
        raise HTTPException(
            429, f"the model provider is rate limiting: {exc}"
        ) from None
    except BudgetExceeded as exc:
        raise HTTPException(
            503,
            f"the live path stopped itself at its own ceiling: {exc} "
            "Raise LIVE_MAX_CALLS or LIVE_MAX_SPEND_USD deliberately.",
        ) from None
    except ScopeViolation as exc:
        raise HTTPException(500, f"scope tripwire fired: {exc}") from None
    except RuntimeError as exc:
        # No credential, no pinned model, or the provider refused outright.
        raise HTTPException(503, f"the live path cannot serve: {exc}") from None
    except psycopg.Error as exc:
        raise HTTPException(500, f"database error: {type(exc).__name__}") from None
    except OSError as exc:
        # urllib raises HTTPError/URLError, both OSError, and `GeminiProvider`
        # re-raises the non-retryable ones as they come. Unhandled, a rejected
        # key would surface as a traceback and a 500 — our fault, when the fact
        # is that the provider said no.
        raise HTTPException(
            502, f"the model provider rejected the request: {exc}"
        ) from None

    return QueryResponse(
        mode="live",
        question=request.question,
        sql=outcome.result["executed_sql"] if outcome.result else None,
        generated_sql=outcome.generated_sql,
        refusal=outcome.refusal,
        error=outcome.error,
        answer=_answer_of(outcome.result) if outcome.result else None,
    )
