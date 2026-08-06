"""Structural checks on the SQL eval set.

These assert; they do not measure (ADR-0005). No model is called and no quota
is spent — this only checks that a committed artifact is internally consistent
and in step with the committed seed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = REPO_ROOT / "evals" / "sql" / "questions.jsonl"
VALID_EXPECTS = {"rows", "empty", "refusal", "disambiguation"}


@pytest.fixture(scope="module")
def questions() -> list[dict]:
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_the_set_is_the_size_adr_0001_asks_for(questions):
    assert 30 <= len(questions) <= 50


def test_ids_are_unique_and_stable(questions):
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))
    assert all(q["id"].startswith("q") for q in questions)


def test_every_question_declares_view_covered(questions):
    """ADR-0001: the threshold is read off the not-view-covered number."""
    for q in questions:
        assert isinstance(q["view_covered"], bool), q["id"]


def test_both_sides_of_view_covered_are_represented(questions):
    covered = [q for q in questions if q["view_covered"]]
    uncovered = [q for q in questions if not q["view_covered"]]
    assert len(covered) >= 5
    # The threshold is judged on these, so there have to be enough to judge on.
    assert len(uncovered) >= 20


def test_expectation_kinds_are_valid(questions):
    for q in questions:
        assert q["expects"] in VALID_EXPECTS, f"{q['id']}: {q['expects']}"


def test_row_questions_have_sql_and_a_non_empty_expectation(questions):
    for q in questions:
        if q["expects"] != "rows":
            continue
        assert q["reference_sql"], f"{q['id']} has no reference SQL"
        assert q["expected"], f"{q['id']} has no expected result set"
        assert q["expected"]["row_count"] > 0, (
            f"{q['id']} expects rows but the reference query returns none — "
            "an empty expectation scores every wrong answer as correct. Use "
            'expects="empty" if empty is the right answer.'
        )


def test_empty_questions_really_are_empty(questions):
    for q in questions:
        if q["expects"] == "empty":
            assert q["expected"]["row_count"] == 0, q["id"]


def test_refusals_and_disambiguations_carry_a_rubric_not_a_result_set(questions):
    for q in questions:
        if q["expects"] not in ("refusal", "disambiguation"):
            continue
        assert q["expected"] is None, f"{q['id']} should not have a result set"
        assert len(q["intent"]) > 60, (
            f"{q['id']} is scored on its rubric, so `intent` has to say what a "
            "correct answer looks like"
        )


def test_the_required_traps_are_all_covered(questions):
    """The set must test what was asked for, not only what is easy to write."""
    present = {trap for q in questions for trap in q["traps"]}
    for required in (
        "signed-quantity",
        "stockout-understates-velocity",
        "point-in-time-vs-current",
        "gst-reform-blending",
        "stock-zero-vs-low",
        "impossible-yoy",
        "explicit-threshold-override",
    ):
        assert required in present, f"no question covers {required}"


def test_stock_policy_is_tested_all_three_ways(questions):
    """A blanket rule would pass one of these and fail the others."""
    stock = [q for q in questions if "stock-zero-vs-low" in q["traps"]]
    kinds = {q["expects"] for q in stock}
    assert len(stock) >= 3
    assert "rows" in kinds
    assert "disambiguation" in kinds, (
        "without an ambiguous case the set teaches a blanket rule about zero"
    )
    sql = " ".join(q["reference_sql"] or "" for q in stock)
    assert "on_hand > 0" in sql, "no question excludes already-out-of-stock"
    assert "on_hand = 0" in sql, "no question targets already-out-of-stock"


def test_every_refusal_has_an_answerable_twin(questions):
    """A refusal on its own teaches refusal of the whole shape.

    q023 refuses a Diwali-over-Diwali comparison; q024 answers the same
    question about Holi, so what is being learned is a judgement about the
    window, not "decline festival comparisons". The same has to hold for the
    other two: q037 refuses to name a cashier while q042 answers the same
    concern at pattern level, and q038 refuses to count customers while q043
    answers about baskets.
    """
    by_id = {q["id"]: q for q in questions}
    refusals = [q for q in questions if q["expects"] == "refusal"]
    assert refusals, "the set has no refusal questions"

    for q in refusals:
        twin_id = q.get("twin")
        assert twin_id, (
            f"{q['id']} is an unpaired refusal — it teaches blanket refusal of "
            "anything in its shape. Give it an answerable twin."
        )
        twin = by_id.get(twin_id)
        assert twin, f"{q['id']} names twin {twin_id}, which does not exist"
        assert twin["expects"] in ("rows", "empty"), (
            f"{q['id']}'s twin {twin_id} is not answerable"
        )
        assert set(q["traps"]) & set(twin["traps"]), (
            f"{q['id']} and {twin_id} share no trap, so the pair does not "
            "isolate the judgement being tested"
        )


def test_the_yoy_family_has_a_refusable_and_an_answerable_case(questions):
    """Both sides, or the set teaches one blanket rule or the other."""
    family = [q for q in questions if "impossible-yoy" in q["traps"]]
    kinds = {q["expects"] for q in family}
    assert "refusal" in kinds, "no year-on-year question the window cannot support"
    assert "rows" in kinds, "no year-on-year question the window CAN support"


def test_expectations_match_the_committed_seed(questions):
    """Regenerating the seed invalidates every expected result set."""
    import hashlib

    fingerprint = hashlib.sha256(
        (REPO_ROOT / "seed" / "CHECKSUMS.txt").read_bytes()
    ).hexdigest()[:16]
    stale = sorted(
        {q["id"] for q in questions if q.get("seed_fingerprint") != fingerprint}
    )
    assert not stale, (
        f"{len(stale)} expectations were computed against a different seed "
        f"({stale[:5]}...). Run `make db && make eval-expectations`."
    )


def test_no_reference_query_uses_wall_clock(questions):
    """as_of_date, never current_date — a wall-clock query returns nothing."""
    for q in questions:
        sql = (q["reference_sql"] or "").lower()
        for banned in ("current_date", "now()", "current_timestamp"):
            assert banned not in sql, f"{q['id']} uses {banned}"


def test_every_ordered_reference_query_has_a_total_order(questions):
    """Unstable ordering silently changes eval scores (ADR-0004).

    A single sort key is fine only when it is already unique — which, for an
    aggregate, means the ORDER BY covers every GROUP BY key. Anything else
    needs an explicit tiebreak.
    """
    for q in questions:
        sql = q["reference_sql"] or ""
        if "ORDER BY" not in sql:
            continue

        order_clause = sql.split("ORDER BY")[-1].split("LIMIT")[0]
        order_keys = {
            key.strip().split()[0] for key in order_clause.split(",") if key.strip()
        }
        if len(order_keys) > 1:
            continue

        if "GROUP BY" in sql:
            group_clause = (
                sql.split("GROUP BY")[-1].split("ORDER BY")[0].split("HAVING")[0]
            )
            group_keys = {key.strip() for key in group_clause.split(",") if key.strip()}
            if group_keys <= order_keys:
                continue  # the sort key is the whole grouping — already unique

        raise AssertionError(
            f"{q['id']} sorts on one non-unique key with no tiebreak: "
            f"{order_clause.strip()}"
        )
