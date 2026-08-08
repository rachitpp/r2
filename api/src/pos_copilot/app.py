"""The query API — demo beat 1.

A question goes in; the answer comes back **beside the SQL that produced it**.
Showing the query is not a debug affordance, it is the product: an answer whose
derivation is invisible cannot be checked, and this project's whole argument is
that unchecked confident answers are the failure that matters.

Scope, per CLAUDE.md rule 5, is applied **before** generation — a clerk's store
is substituted into the query — and `check_scope` runs afterwards only as a
tripwire that refuses rather than filters.

Demo mode is the default and needs no key (rule 2). The live model path is not
wired here yet.
"""

from __future__ import annotations

import os
from typing import Literal

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pos_copilot import demo
from pos_copilot.readonly_sql import (
    DEFAULT_MAX_ROWS,
    ScopeViolation,
    UnsafeQuery,
    execute,
)

app = FastAPI(
    title="POS Copilot",
    description="Ask about the shop in English; get the answer and the SQL.",
    version="0.1.0",
)

#: Which stores a role may see. `None` means chain-wide.
#: This is the whole of role-scoping for Phase 1 — deliberately small, and
#: deliberately consulted BEFORE the query is built rather than after it runs.
UNSCOPED_ROLES = frozenset({"manager", "owner"})


def readonly_url() -> str:
    url = os.environ.get("READONLY_DATABASE_URL")
    if not url:
        raise HTTPException(500, "READONLY_DATABASE_URL is not set")
    return url


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "true").strip().lower() not in ("false", "0")


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
    #: Set when the honest answer is that the data cannot support the question.
    refusal: str | None
    answer: Answer | None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": "demo" if demo_mode() else "live"}


@app.get("/demo/questions", response_model=list[DemoQuestion])
def demo_questions() -> list[dict]:
    """What demo mode can answer, what each needs, and what each will do.

    A bare list of strings would force the caller to infer which questions are
    store-scoped, and an inferring caller guesses and defaults — the failure
    `DemoPair.resolve` exists to prevent, one layer up.
    """
    return demo.catalogue()


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not demo_mode():
        raise HTTPException(
            501,
            "the live model path is not wired yet — run with DEMO_MODE=true",
        )

    # Scope is decided here, before any SQL exists.
    visible = None if request.role in UNSCOPED_ROLES else {request.store_id or 0}
    store_id = request.store_id

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
        sql = pair.resolve(store_id)
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
        answer=Answer(
            columns=result["columns"],
            rows=result["rows"],
            row_count=result["row_count"],
            total_row_count=result["total_row_count"],
            truncated=result["truncated"],
            notice=result["notice"],
        ),
    )
