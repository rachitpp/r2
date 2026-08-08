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

import pytest
from fastapi.testclient import TestClient

from pos_copilot import demo
from pos_copilot.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


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


def test_live_mode_is_honest_about_not_being_wired(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    r = client.post("/query", json={"question": "What was our revenue last month?"})
    assert r.status_code == 501


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
