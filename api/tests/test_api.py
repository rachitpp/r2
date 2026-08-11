"""The query endpoint — demo beat 1.

The behaviour worth asserting is not "it returns 200". It is that the answer
arrives **beside the SQL that produced it**, that a question the data cannot
support comes back as a refusal rather than a guess, and that scope is in the
query rather than applied to the rows afterwards (CLAUDE.md rule 5).

Demo mode needs no key and no quota, so all of this runs in CI except the
handful marked `db`.
"""

from __future__ import annotations

import os
import urllib.error

import pytest
from fastapi.testclient import TestClient

from pos_copilot import demo
from pos_copilot import live as live_mod
from pos_copilot.app import app
from pos_copilot.model import RateLimited, StubProvider

client = TestClient(app)


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


#: Captured at import, so teardown clears the real caches even while the `live`
#: fixture has `provider` monkeypatched to a stub that has none.
_LIVE_CACHES = (live_mod.provider, live_mod.budget)


@pytest.fixture(autouse=True)
def _reset_live_state():
    """The provider and the budget are process-wide by design, so reset them.

    A budget leaked from one test makes a later one fail at its ceiling for a
    reason that has nothing to do with what it is testing.
    """
    for cached in _LIVE_CACHES:
        cached.cache_clear()
    yield
    for cached in _LIVE_CACHES:
        cached.cache_clear()


@pytest.fixture
def live(monkeypatch):
    """Live mode against a stub provider: no key, no quota, no network.

    Rule 1 — nothing in CI may need a model call — and the stub is also why a
    real credential's first use is not also the first time this code has run.
    """
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("AS_OF_DATE", "2026-06-30")
    stub = StubProvider(responses={})
    monkeypatch.setattr(live_mod, "provider", lambda: stub)
    return stub


@pytest.fixture
def readonly(monkeypatch):
    url = os.environ.get("TEST_READONLY_URL")
    if not url:
        pytest.skip("TEST_READONLY_URL is not set")
    monkeypatch.setenv("READONLY_DATABASE_URL", url)
    return url


# ── The demo fixture file itself ─────────────────────────────────────────────


def test_every_store_scoped_pair_carries_the_scope_token():
    """Rule 5 in the fixture: a scoped pair whose SQL has no `{store_id}` would
    silently answer chain-wide for a user who may see one store."""
    for pair in demo.load().values():
        if pair.store_scoped:
            assert demo.STORE_TOKEN in (pair.sql or "")


def test_every_pair_answers_or_refuses():
    for pair in demo.load().values():
        assert pair.sql or pair.refusal


def test_the_demo_set_is_not_the_eval_set():
    """Two artifacts, two purposes. The eval references are the instrument and
    are under repair; serving answers from them would ship known-wrong numbers.
    """
    import json

    questions = demo.API_ROOT.parent / "evals" / "sql" / "questions.jsonl"
    refs = {
        json.loads(line).get("reference_sql")
        for line in questions.read_text().splitlines()
    }
    for pair in demo.load().values():
        if pair.sql:
            assert pair.sql not in refs


# ── Matching ─────────────────────────────────────────────────────────────────


def test_matching_ignores_punctuation_and_case():
    assert demo.normalise("What was our revenue last month?") == demo.normalise(
        "what was our REVENUE last month"
    )


def test_an_unknown_question_is_a_boundary_not_a_guess():
    with pytest.raises(demo.DemoUnavailable):
        demo.lookup("what will sales be next quarter")


def test_a_scoped_question_without_a_store_refuses_rather_than_defaulting():
    """Defaulting to store 1 would answer the wrong shop without saying so."""
    pair = demo.lookup("What's about to run out at our store this week?")
    with pytest.raises(demo.DemoUnavailable):
        pair.resolve(None)


def test_scope_is_substituted_into_the_query():
    pair = demo.lookup("What's about to run out at our store this week?")
    assert "store_id = 3" in pair.resolve(3)
    assert demo.STORE_TOKEN not in pair.resolve(3)


# ── The endpoint ─────────────────────────────────────────────────────────────


def test_health_reports_the_mode():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "demo"


def test_the_catalogue_lists_what_demo_mode_can_answer():
    listed = {q["question"] for q in client.get("/demo/questions").json()}
    assert listed == {p.question for p in demo.load().values()}


def test_the_catalogue_says_which_questions_need_a_store():
    """Otherwise the caller infers, and an inferring caller guesses and
    defaults — the exact thing `resolve` refuses to do, one layer up."""
    listed = {q["question"]: q for q in client.get("/demo/questions").json()}
    for pair in demo.load().values():
        assert listed[pair.question]["requires_store"] is pair.store_scoped


def test_the_refusal_is_offered_deliberately_not_stumbled_into():
    """The refusal is the strongest beat in the demo. A reader should be able to
    pick it from the list knowing what it demonstrates."""
    listed = client.get("/demo/questions").json()
    refusals = [q for q in listed if q["expect"] == "refusal"]
    assert [q["question"] for q in refusals] == ["How many customers do we have?"]


def test_every_catalogued_question_is_actually_askable():
    """A catalogue that lists something /query rejects is worse than no
    catalogue — it sends the caller at a wall it advertised as a door."""
    for entry in client.get("/demo/questions").json():
        payload = {"question": entry["question"]}
        if entry["requires_store"]:
            payload |= {"role": "clerk", "store_id": 1}
        assert client.post("/query", json=payload).status_code in (200, 500)


def test_a_question_the_data_cannot_support_returns_a_refusal_not_a_guess():
    body = client.post(
        "/query", json={"question": "How many customers do we have?"}
    ).json()
    assert body["answer"] is None
    assert body["sql"] is None
    assert "INSUFFICIENT SCHEMA" in body["refusal"]


def test_an_unknown_question_is_404_and_says_why():
    r = client.post("/query", json={"question": "what will sales be next quarter"})
    assert r.status_code == 404
    assert "fixed set" in r.json()["detail"]


def test_an_empty_question_is_rejected():
    assert client.post("/query", json={"question": ""}).status_code == 422


# ── The live model path ──────────────────────────────────────────────────────
#
# Every test below runs against `StubProvider`. What is asserted is the plumbing
# and the refusals; how good the model's SQL is belongs to the eval, which
# measures rather than asserts (ADR-0005).


def test_health_says_so_when_live_mode_cannot_actually_serve(monkeypatch):
    """Answering `ok` with no credential would be the recurring defect class in
    the one endpoint whose whole job is reporting state."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.delenv("MODEL_PLAN", raising=False)
    body = client.get("/health").json()
    assert body["mode"] == "live"
    assert body["status"] == "unconfigured"
    assert "MODEL_PLAN" in body["detail"]


def test_health_names_the_pinned_model_when_live_is_configured(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("MODEL_PLAN", "gemini-3.6-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert client.get("/health").json() == {
        "status": "ok",
        "provider": "gemini",
        "model": "gemini-3.6-flash",
        "mode": "live",
    }


def test_live_mode_without_a_credential_says_what_is_missing(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.delenv("MODEL_PLAN", raising=False)
    r = client.post("/query", json={"question": "What was our revenue last month?"})
    assert r.status_code == 503
    assert "MODEL_PLAN" in r.json()["detail"]


def test_the_prompt_carries_the_anchor_date_and_the_scope(live):
    """`current_date` silently returns nothing past the anchor, and the scope
    has to be in the prompt for rule 5 to be honoured at all."""
    question = "What was our revenue last month?"
    live.responses[question] = "-- INSUFFICIENT SCHEMA: not what this test is for"
    client.post("/query", json={"question": question})
    (prompt,) = live.calls
    assert "Today's date is 2026-06-30" in prompt
    assert "Their data scope: all stores" in prompt


def test_a_refusal_sentinel_comes_back_as_a_refusal_not_an_error(live):
    question = "How many customers do we have?"
    live.responses[question] = "-- INSUFFICIENT SCHEMA: there is no customer table"
    body = client.post("/query", json={"question": question}).json()
    assert body["mode"] == "live"
    assert body["refusal"].startswith("-- INSUFFICIENT SCHEMA")
    assert body["error"] is None
    assert body["sql"] is None and body["answer"] is None


def test_an_out_of_scope_sentinel_is_a_refusal_too_and_stays_distinct(live):
    """Two sentinels, never folded together: one says the database cannot answer
    this for anyone, the other that it can but not for this user."""
    question = "What did Nagpur take last week?"
    live.responses[question] = "-- OUT OF SCOPE: this user can only see store_id = 1"
    body = client.post("/query", json={"question": question}).json()
    assert body["refusal"].startswith("-- OUT OF SCOPE")
    assert body["error"] is None


def test_unsafe_generated_sql_is_refused_before_execution_and_still_shown(live):
    """The guard is the enforcement (rule 4), and the refused query is shown —
    a query you cannot see is a query you cannot check."""
    question = "Get rid of last month"
    live.responses[question] = "DROP TABLE sales"
    body = client.post("/query", json={"question": question}).json()
    assert body["answer"] is None and body["sql"] is None
    assert body["generated_sql"] == "DROP TABLE sales"
    assert "refused before execution" in body["error"]
    assert body["refusal"] is None


def test_a_scoped_request_with_no_store_is_refused_before_the_model_is_called(live):
    """Rule 5 is a sequencing claim, so the assertion is about sequence: no
    call was made, because there was nothing safe to ask."""
    r = client.post("/query", json={"question": "What is low?", "role": "clerk"})
    assert r.status_code == 422
    assert live.calls == []


def test_the_live_path_stops_itself_at_its_own_ceiling(live, monkeypatch):
    """Rule 2: every runner carries a call ceiling. This one's loop is held by
    whoever has the browser's refresh key."""
    monkeypatch.setenv("LIVE_MAX_CALLS", "1")
    live_mod.budget.cache_clear()
    payload = {"question": "What was our revenue last month?"}
    assert client.post("/query", json=payload).status_code == 200
    second = client.post("/query", json=payload)
    assert second.status_code == 503
    assert "ceiling" in second.json()["detail"]
    assert len(live.calls) == 1


class _RefusingProvider:
    """A provider that only fails. Cheaper than a real key saying no."""

    name = "stub"
    model = "stub-v1"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def generate(self, prompt: str) -> str:
        raise self.exc


def test_a_rate_limited_provider_is_a_429_not_a_503(live, monkeypatch):
    """`RateLimited` and `BudgetExceeded` are both `RuntimeError` subclasses, so
    the order they are caught in decides the status code. Asserted, not assumed."""
    monkeypatch.setattr(
        live_mod, "provider", lambda: _RefusingProvider(RateLimited("429 x6"))
    )
    r = client.post("/query", json={"question": "What was our revenue last month?"})
    assert r.status_code == 429
    assert "rate limiting" in r.json()["detail"]


def test_a_provider_that_rejects_the_request_is_a_502_not_a_traceback(
    live, monkeypatch
):
    """urllib's errors are `OSError`, not `RuntimeError`. Uncaught, a refused key
    would report the provider's "no" as a fault of ours."""
    refused = urllib.error.HTTPError("https://x", 403, "forbidden", {}, None)  # type: ignore[arg-type]
    monkeypatch.setattr(live_mod, "provider", lambda: _RefusingProvider(refused))
    r = client.post("/query", json={"question": "What was our revenue last month?"})
    assert r.status_code == 502
    assert "provider rejected" in r.json()["detail"]


@pytest.mark.db
def test_a_generated_answer_comes_back_beside_the_sql_that_ran(live, readonly):
    question = "What did we take last month?"
    live.responses[question] = (
        "SELECT sum(subtotal) AS net_revenue FROM sales "
        "WHERE business_date >= DATE '2026-05-01' "
        "AND business_date < DATE '2026-06-01'"
    )
    body = client.post("/query", json={"question": question}).json()
    assert body["mode"] == "live"
    assert body["answer"]["row_count"] == 1
    assert "net_revenue" in body["answer"]["columns"]
    # Both, because either one alone hides something: `sql` is what ran, wrapper
    # and cap included; `generated_sql` is what the model actually wrote.
    assert "_guarded" in body["sql"]
    assert "_guarded" not in body["generated_sql"]


@pytest.mark.db
def test_a_generated_query_that_fails_says_so_and_shows_the_query(live, readonly):
    """Wrong-and-obvious, which `sql_generate.md` prefers to wrong-and-plausible.
    A 500 here would report the model's bad query as a server fault."""
    question = "Ask for something that is not in the schema"
    live.responses[question] = "SELECT * FROM no_such_table"
    r = client.post("/query", json={"question": question})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] is None
    assert body["generated_sql"] == "SELECT * FROM no_such_table"
    assert "failed to execute" in body["error"]


@pytest.mark.db
def test_a_scoped_prompt_carries_the_predicate_and_the_store_name(live, readonly):
    """The measured shape — `store_id = 1 (Kothrud, Pune)` — carries the
    predicate itself. Phrasing it differently here would put this path
    off-distribution from the 47x3 run that measured it."""
    question = "What is about to run out?"
    live.responses[question] = "-- INSUFFICIENT SCHEMA: not what this test is for"
    client.post("/query", json={"question": question, "role": "clerk", "store_id": 1})
    (prompt,) = live.calls
    assert "Their data scope: store_id = 1 (Kothrud, Pune)" in prompt


@pytest.mark.db
def test_an_unknown_store_is_a_404_rather_than_a_scope_matching_nobody(live, readonly):
    r = client.post(
        "/query", json={"question": "What is low?", "role": "clerk", "store_id": 99}
    )
    assert r.status_code == 404
    assert live.calls == []


@pytest.mark.db
def test_the_answer_comes_back_beside_the_sql_that_produced_it(readonly):
    body = client.post(
        "/query", json={"question": "What was our revenue last month?"}
    ).json()
    assert body["answer"]["row_count"] == 1
    assert "net_revenue" in body["answer"]["columns"]
    # The SQL shown is what actually ran — wrapper included, nothing hidden.
    assert "_guarded" in body["sql"]
    assert "LIMIT" in body["sql"]


@pytest.mark.db
def test_a_clerk_sees_only_their_own_store(readonly):
    body = client.post(
        "/query",
        json={
            "question": "What's about to run out at our store this week?",
            "role": "clerk",
            "store_id": 2,
        },
    ).json()
    assert "store_id = 2" in body["sql"]
    assert body["answer"]["row_count"] > 0


@pytest.mark.db
def test_the_scope_predicate_is_in_the_query_not_applied_afterwards(readonly):
    """Rule 5. The proof is that the store id appears in the executed SQL."""
    body = client.post(
        "/query",
        json={
            "question": "What's about to run out at our store this week?",
            "role": "clerk",
            "store_id": 1,
        },
    ).json()
    assert "WHERE store_id = 1" in body["sql"]


@pytest.mark.db
def test_a_truncated_answer_says_so(readonly):
    body = client.post(
        "/query",
        json={
            "question": "What's about to run out at our store this week?",
            "role": "clerk",
            "store_id": 1,
            "max_rows": 5,
        },
    ).json()
    assert body["answer"]["truncated"] is True
    assert body["answer"]["row_count"] == 5
    assert body["answer"]["total_row_count"] > 5
    assert "showing the first 5" in body["answer"]["notice"]
