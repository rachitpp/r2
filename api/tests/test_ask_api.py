"""Assertions for `/ask` — demo beat 2's boundary.

These exercise the parts that do not need a database or a model: request
validation, scope refusal, and the demo lookup's date keying. The retrieval
itself is covered in `test_retrieve.py`, and the end-to-end behaviour is
committed as an artifact by `make demo-beat-2` rather than asserted here — a
test that needs Postgres, a model and 3 paid calls is a test that does not run.

**The refusal tests are the load-bearing ones.** Rule 5 says scope is decided
before generation, and for this endpoint "before generation" means before
retrieval runs at all — so a scoped role with no store must be a 422 from the
boundary, not an empty result set from the query.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pos_copilot import demo
from pos_copilot.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


class TestValidation:
    def test_a_missing_date_is_rejected(self):
        """`as_of` has no default on purpose. This data has a fixed end date, so
        defaulting to today would silently retrieve nothing — and the date is
        the variable this whole beat is about."""
        response = client.post("/ask", json={"question": "payment terms?"})
        assert response.status_code == 422

    def test_a_malformed_date_is_rejected_with_the_value(self):
        response = client.post(
            "/ask", json={"question": "payment terms?", "as_of": "15-01-2025"}
        )
        assert response.status_code == 422
        assert "15-01-2025" in response.json()["detail"]

    def test_an_empty_question_is_rejected(self):
        response = client.post("/ask", json={"question": "", "as_of": "2025-01-15"})
        assert response.status_code == 422


class TestScopeRefusal:
    def test_a_clerk_without_a_store_is_refused_before_retrieval(self):
        """Rule 5. Not an empty result — a refusal, from the boundary, before
        any retrieval runs. Answering would mean picking a store, and a
        defaulted store is the wrong shop's documents wearing the right shop's
        label."""
        response = client.post(
            "/ask",
            json={
                "question": "payment terms?",
                "as_of": "2025-01-15",
                "role": "clerk",
            },
        )
        assert response.status_code == 422
        assert "store" in response.json()["detail"].lower()

    def test_an_owner_without_a_store_is_not_refused_for_scope(self):
        """An unscoped role legitimately has no store. Whatever happens next,
        it must not be the scope refusal — otherwise the check is rejecting
        everyone and looks like it works."""
        response = client.post(
            "/ask",
            json={"question": "payment terms?", "as_of": "2025-01-15", "role": "owner"},
        )
        if response.status_code == 422:
            assert "store" not in response.json()["detail"].lower()


class TestDemoCatalogue:
    def test_the_catalogue_carries_dates_not_just_questions(self):
        """The date is part of the key, so a UI that offered the question alone
        would let a reader pick a combination with no answer and read the 404 as
        the system being broken."""
        entries = client.get("/demo/document-questions").json()
        assert entries
        for entry in entries:
            assert entry["as_of"], "a catalogue entry with no date is unusable"
            assert entry["question"]

    def test_the_catalogue_offers_both_sides_of_the_renegotiation(self):
        """Demo beat 2 is one question at two dates. A catalogue with only one
        of them cannot demonstrate it."""
        entries = client.get("/demo/document-questions").json()
        terms = [e for e in entries if "Sahyadri" in e["question"]]
        assert len({e["as_of"] for e in terms}) >= 2

    def test_the_catalogue_offers_the_none_in_force_case(self):
        """The harder half. Without it a reader only ever sees the easy beat."""
        entries = client.get("/demo/document-questions").json()
        assert any(e["outcome"] == "none_in_force" for e in entries)


class TestDemoLookup:
    def test_an_unlisted_date_has_no_answer_and_no_fallback(self):
        """Serving a neighbouring date's answer would be the demo contradicting
        the exact property it exists to show."""
        with pytest.raises(demo.DemoUnavailable):
            demo.lookup_document(
                "What are the payment terms for Sahyadri Agro Traders?", "2025-03-01"
            )

    def test_the_two_recorded_dates_give_different_answers(self):
        """If they matched, the demo would be showing a search box."""
        before = demo.lookup_document(
            "What are the payment terms for Sahyadri Agro Traders?", "2025-01-15"
        )
        after = demo.lookup_document(
            "What are the payment terms for Sahyadri Agro Traders?", "2026-06-30"
        )
        assert before.answer and after.answer
        assert before.answer != after.answer
        assert "14" in before.answer
        assert "30" in after.answer

    def test_the_gap_case_stores_no_answer_at_all(self):
        """Not a missing value. The live path makes NO MODEL CALL there, so
        there is no output to replay, and writing a sentence would invent one."""
        gap = demo.lookup_document("What are the payment terms?", "2025-11-15")
        assert gap.answer is None
        assert gap.outcome == "none_in_force"
