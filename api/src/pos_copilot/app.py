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

import json
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


def app_url() -> str:
    """The read/write connection. Queueing a run is a write, and the read-only
    role must not be able to make one — the same separation that stops the role
    generated SQL runs under from approving anything (migration 005's grants)."""
    url = env.text("DATABASE_URL")
    if not url:
        raise HTTPException(500, "DATABASE_URL is not set")
    return url


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


# ─────────────────────────────────────────────────────────────────────────────
# Demo beat 2 — grounded document Q&A
#
# Retrieval is local and free (rule 2), so it runs for real in BOTH modes and
# only the answer text differs: replayed in demo mode, generated in live mode.
# A reader with no key still sees the citations retrieval actually produced.
#
# Rule 5 is enforced in `retrieve()`'s WHERE clause and rule 7 alongside it, so
# a chunk outside the caller's scope or outside the requested date is never
# fetched. This layer decides the scope BEFORE retrieval, exactly as `/query`
# decides it before any SQL exists.
# ─────────────────────────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    #: The date the question is asked "as of". Required, never defaulted to
    #: today: this system's data has a fixed end date, so wall-clock would
    #: silently retrieve nothing — and the date is the whole point of beat 2.
    as_of: str = Field(min_length=10, max_length=10)
    role: Literal["clerk", "manager", "owner"] = "owner"
    store_id: int | None = Field(default=None, ge=1)
    supplier_code: str | None = Field(default=None, max_length=16)
    doc_types: list[str] | None = None


class Citation(BaseModel):
    doc_id: str
    doc_type: str
    effective_from: str
    effective_to: str | None
    similarity: float
    #: The chunk text itself. Shown, never hidden — an answer whose sources you
    #: cannot read is an answer you cannot check, which is the same reason
    #: `/query` returns the SQL it ran.
    content: str


class AskResponse(BaseModel):
    mode: Literal["demo", "live"]
    question: str
    as_of: str
    #: "answered" | "none_in_force" | "not_found"
    #:
    #: The last two are NOT the same and the UI must not collapse them. "No
    #: contract covered that month" and "we hold nothing for this supplier" are
    #: different answers to different questions, and telling them apart is what
    #: demo beat 2 exists to show.
    outcome: str
    answer: str | None
    citations: list[Citation]
    #: True when no model call was made. Always true for none_in_force and
    #: not_found, because there is nothing to ground an answer in and spending a
    #: call to say so would give the model the chance to answer from general
    #: knowledge instead.
    grounded_without_model: bool


@app.get("/demo/document-questions", response_model=list[dict])
def demo_document_questions() -> list[dict]:
    """Question AND date pairs demo mode can replay.

    The date is part of the key, so it is part of the catalogue. A UI offering
    the question without its dates would let a reader pick a combination with no
    answer and read the 404 as the system being broken.
    """
    return demo.document_catalogue()


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    from datetime import date as _date

    from pos_copilot import docqa
    from pos_copilot.embed import default_embedder
    from pos_copilot.retrieve import retrieve, store_scope_for

    try:
        on = _date.fromisoformat(request.as_of)
    except ValueError:
        raise HTTPException(422, f"as_of is not a date: {request.as_of!r}") from None

    # Scope is decided here, before retrieval runs and before a prompt exists.
    try:
        store_scope = store_scope_for(request.role, request.store_id)
    except StoreRequired as exc:
        raise HTTPException(422, str(exc)) from None

    supplier_id = None
    try:
        with psycopg.connect(readonly_url()) as conn:
            if request.supplier_code:
                with conn.cursor() as cur:
                    cur.execute(
                        "select supplier_id from suppliers where code = %s",
                        (request.supplier_code,),
                    )
                    row = cur.fetchone()
                if row is None:
                    raise HTTPException(
                        404, f"no supplier with code {request.supplier_code!r}"
                    )
                supplier_id = row[0]

            embedder = default_embedder()

            if demo_mode():
                found = retrieve(
                    conn,
                    request.question,
                    as_of=on,
                    embedder=embedder,
                    supplier_id=supplier_id,
                    store_id=store_scope,
                    doc_types=request.doc_types,
                )
                try:
                    replay = demo.lookup_document(request.question, request.as_of)
                except demo.DemoUnavailable as exc:
                    raise HTTPException(404, str(exc)) from None
                # The replayed answer is only used when retrieval agrees there
                # is something to answer from. If retrieval says nothing is in
                # force, that wins — the demo must not narrate over the data.
                outcome = found.outcome
                answer = replay.answer if found.found else None
                chunks = found.chunks
            else:
                got = docqa.ask(
                    conn,
                    request.question,
                    embedder=embedder,
                    as_of=on,
                    supplier_id=supplier_id,
                    store_id=store_scope,
                    doc_types=request.doc_types,
                )
                if got.outcome == "error":
                    raise HTTPException(502, got.error or "generation failed")
                outcome, answer, chunks = got.outcome, got.answer, got.chunks
    except psycopg.OperationalError as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from None

    return AskResponse(
        mode="demo" if demo_mode() else "live",
        question=request.question,
        as_of=request.as_of,
        outcome=outcome,
        answer=answer,
        citations=[
            Citation(
                doc_id=c.doc_id,
                doc_type=c.doc_type,
                effective_from=str(c.effective_from),
                effective_to=str(c.effective_to) if c.effective_to else None,
                similarity=round(c.similarity, 4),
                content=c.content,
            )
            for c in chunks
        ],
        grounded_without_model=(outcome != "answered") or demo_mode(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — agent runs
#
# `POST /runs` writes a row and returns an id. It does NOT run the agent: the
# work happens in `scripts/worker.py`, which is what makes "survives a server
# restart" true and what keeps a request handler from holding a connection open
# across a paced model call.
#
# Rule 5 is enforced twice on purpose — here, so a scoped role with no store is
# a 422 rather than a row, and again by `agent_runs_scoped_role_has_store` in the
# schema, so no other path can queue one either.
# ─────────────────────────────────────────────────────────────────────────────


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    role: Literal["clerk", "manager", "owner"] = "owner"
    store_id: int | None = Field(default=None, ge=1)
    requested_by: str = Field(min_length=1, max_length=64)
    #: Rule 3. Sent by the caller but bounded here, because a ceiling a client
    #: can raise is not a ceiling.
    max_tool_calls: int = Field(default=6, ge=1, le=6)


class RunAccepted(BaseModel):
    agent_run_id: int
    status: str


@app.post("/runs", response_model=RunAccepted, status_code=202)
def create_run(request: RunRequest) -> RunAccepted:
    """202, not 200. Nothing has happened yet and the response says so."""
    from pos_copilot import runs as run_store
    from pos_copilot.readonly_sql import StoreRequired as _StoreRequired

    try:
        visible_stores(request.role, request.store_id)
    except _StoreRequired as exc:
        raise HTTPException(422, str(exc)) from None

    try:
        with psycopg.connect(app_url()) as conn:
            run_id = run_store.enqueue(
                conn,
                request.prompt,
                requested_by=request.requested_by,
                role=request.role,
                store_id=request.store_id,
                max_tool_calls=request.max_tool_calls,
            )
    except psycopg.OperationalError as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from None
    return RunAccepted(agent_run_id=run_id, status="queued")


@app.get("/runs/{agent_run_id}")
def get_run(agent_run_id: int) -> dict:
    """The run, its proposals and its whole audit trail.

    The events are returned with it rather than behind a second endpoint: the
    audit log is the point of storing state as rows (ADR-0003), and a UI that
    has to ask twice will show the state without the explanation.
    """
    from pos_copilot import runs as run_store

    try:
        with psycopg.connect(readonly_url()) as conn:
            run = run_store.load_run(conn, agent_run_id)
    except psycopg.OperationalError as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from None
    if run is None:
        raise HTTPException(404, f"no run {agent_run_id}")
    return json.loads(json.dumps(run, default=str))
