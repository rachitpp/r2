"""The eval runner's parts: pacing, caching, prompt hashing, scoring.

None of this calls a model. The runner is built and proven against a stub so
that plumbing bugs are found for free rather than for quota.
"""

from __future__ import annotations

import pytest

from pos_copilot.model import Pacer, ResponseCache, StubProvider
from pos_copilot.prompts import bundle_fingerprint, load_sql_prompt
from pos_copilot.scoring import (
    Judgement,
    Outcome,
    compare,
    judge,
    normalise,
    strip_fences,
)

# ── Pacing and backoff ───────────────────────────────────────────────────────


def test_min_interval_comes_from_the_rpm_allowance():
    assert Pacer(rpm=10).min_interval == 6.0
    assert Pacer(rpm=15).min_interval == 4.0


def test_the_pacer_waits_between_request_starts():
    slept: list[float] = []
    now = [0.0]
    pacer = Pacer(rpm=10)
    pacer.wait_turn(sleep=slept.append, clock=lambda: now[0])
    now[0] = 1.0
    pacer.wait_turn(sleep=slept.append, clock=lambda: now[0])
    assert slept == [5.0], "second request should wait out the remaining interval"


def test_the_pacer_does_not_wait_when_the_interval_has_already_passed():
    slept: list[float] = []
    now = [0.0]
    pacer = Pacer(rpm=10)
    pacer.wait_turn(sleep=slept.append, clock=lambda: now[0])
    now[0] = 99.0
    pacer.wait_turn(sleep=slept.append, clock=lambda: now[0])
    assert slept == []


def test_backoff_grows_exponentially_and_is_capped():
    pacer = Pacer(base_delay=2.0, max_delay=30.0)
    ceilings = [min(30.0, 2.0 * 2**attempt) for attempt in range(8)]
    for attempt, ceiling in enumerate(ceilings):
        assert 0.0 <= pacer.backoff_delay(attempt) <= ceiling


def test_backoff_is_jittered_rather_than_a_fixed_ladder():
    pacer = Pacer()
    draws = {round(pacer.backoff_delay(4), 6) for _ in range(20)}
    assert len(draws) > 1, "a constant delay would synchronise retries"


# ── The cache ────────────────────────────────────────────────────────────────


def test_cache_round_trips_on_the_full_key(tmp_path):
    cache = ResponseCache(root=tmp_path)
    cache.put("fp1", "q001", 0, "SELECT 1")
    assert cache.get("fp1", "q001", 0) == "SELECT 1"


def test_each_run_index_is_cached_separately(tmp_path):
    """Cross-run variance needs three genuinely separate responses."""
    cache = ResponseCache(root=tmp_path)
    cache.put("fp1", "q001", 0, "first")
    assert cache.get("fp1", "q001", 1) is None
    cache.put("fp1", "q001", 1, "second")
    assert cache.get("fp1", "q001", 0) == "first"
    assert cache.get("fp1", "q001", 1) == "second"


def test_a_changed_prompt_invalidates_the_cache(tmp_path):
    """Editing business_context.md must not reuse answers to the old prompt."""
    cache = ResponseCache(root=tmp_path)
    cache.put("fp1", "q001", 0, "old answer")
    assert cache.get("fp2", "q001", 0) is None


def test_a_changed_question_invalidates_its_own_cached_answer(tmp_path):
    """The prompt fingerprint does not cover the question text.

    Replacing a question changes what the model would be asked while changing no
    part of the key, so without this the next re-score judges the answer to the
    old question against the new one and reports it as a result. Found the hard
    way: q049 was withdrawn on 2026-08-08 and its three responses had to be
    deleted by hand.
    """
    cache = ResponseCache(root=tmp_path)
    cache.put("fp1", "q049", 0, "old answer", "the original question")
    assert cache.get("fp1", "q049", 0, "the original question") == "old answer"
    assert cache.get("fp1", "q049", 0, "a REPLACED question") is None
    assert cache.stale == 1


def test_an_answer_cached_before_question_hashing_is_still_usable(tmp_path):
    """Rejecting them would have voided 288 paid-for responses. The
    grandfathering ends by itself: the next prompt change starts a new
    directory, and everything in it carries the hash."""
    import json

    path = tmp_path / "fp1"
    path.mkdir()
    (path / "q001.0.json").write_text(json.dumps({"response": "older format"}))
    cache = ResponseCache(root=tmp_path)
    assert cache.get("fp1", "q001", 0, "any question at all") == "older format"
    assert cache.stale == 0


def test_cache_can_be_disabled(tmp_path):
    cache = ResponseCache(root=tmp_path, enabled=False)
    cache.put("fp1", "q001", 0, "x")
    assert cache.get("fp1", "q001", 0) is None


# ── Prompt loading and hashing ───────────────────────────────────────────────


def test_the_prompt_bundle_hashes_every_file_that_reaches_the_model():
    bundle = load_sql_prompt()
    assert set(bundle.hashes) == {
        "sql_generate.md",
        "context/business_context.md",
        "context/schema.md",
    }
    assert all(len(h) == 64 for h in bundle.hashes.values())


def test_the_fingerprint_changes_when_any_file_changes():
    base = {"a.md": "1" * 64, "b.md": "2" * 64}
    changed = {"a.md": "1" * 64, "b.md": "3" * 64}
    assert bundle_fingerprint(base) != bundle_fingerprint(changed)


def test_the_fingerprint_is_order_independent():
    assert bundle_fingerprint({"a": "1", "b": "2"}) == bundle_fingerprint(
        {"b": "2", "a": "1"}
    )


def test_rendering_supplies_every_placeholder_the_prompt_needs():
    bundle = load_sql_prompt()
    rendered = bundle.render(
        question="test",
        as_of_date="2026-06-30",
        user_role="clerk",
        store_scope="store_id = 1 (Kothrud, Pune)",
    )
    assert "test" in rendered
    assert "store_id = 1 (Kothrud, Pune)" in rendered
    assert "{" not in rendered.split("# Examples")[0].replace("{{", "").replace(
        "}}", ""
    )


def test_a_missing_placeholder_fails_loudly():
    bundle = load_sql_prompt()
    with pytest.raises(KeyError, match="store_scope"):
        bundle.render(question="q", as_of_date="2026-06-30", user_role="clerk")


# ── Scoring ──────────────────────────────────────────────────────────────────


def test_markdown_fences_are_stripped():
    assert strip_fences("```sql\nSELECT 1\n```") == "SELECT 1"
    assert strip_fences("```\nSELECT 1\n```") == "SELECT 1"
    assert strip_fences("SELECT 1") == "SELECT 1"


def test_formatting_differences_are_not_wrong_answers():
    """Otherwise silent-wrong fills with noise and looks like the trap firing."""
    assert normalise("1234.50") == normalise(1234.5)
    assert normalise("10") == normalise(10)
    assert normalise(" Pune ") == normalise("pune")


def test_identical_result_sets_are_correct():
    result = {"rows": [[1, "a"], [2, "b"]]}
    assert compare(result, result).outcome is Outcome.CORRECT


def test_same_rows_in_a_different_order_is_its_own_failure():
    """Diagnostically distinct — it means a missing ORDER BY tiebreak."""
    verdict = compare({"rows": [[1], [2]]}, {"rows": [[2], [1]]})
    assert verdict.outcome is Outcome.WRONG_ORDER
    assert verdict.outcome.is_silent_wrong


def test_different_values_are_silent_wrong():
    verdict = compare({"rows": [[1], [2]]}, {"rows": [[1], [99]]})
    assert verdict.outcome is Outcome.WRONG_ROWS
    assert verdict.outcome.is_silent_wrong


def test_an_execution_error_is_not_silent_wrong():
    """It broke visibly. That is recoverable; a confident wrong number is not."""
    assert not Outcome.EXECUTION_ERROR.is_silent_wrong


def test_answering_a_question_that_should_be_refused_is_silent_wrong():
    q = {"expects": "refusal", "id": "q023"}
    verdict = judge(q, "SELECT 1", {"rows": [[1]], "row_count": 1}, None)
    assert verdict.outcome is Outcome.SHOULD_HAVE_REFUSED
    assert verdict.outcome.is_silent_wrong


def test_the_two_refusal_sentinels_are_not_interchangeable():
    """A schema gap and a permission boundary are different capabilities."""
    scope_q = {"expects": "out_of_scope", "id": "q044"}
    verdict = judge(scope_q, "-- INSUFFICIENT SCHEMA: nope", None, None)
    assert verdict.outcome is Outcome.WRONG_REFUSAL_KIND

    schema_q = {"expects": "refusal", "id": "q038"}
    verdict = judge(schema_q, "-- OUT OF SCOPE: nope", None, None)
    assert verdict.outcome is Outcome.WRONG_REFUSAL_KIND


def test_each_sentinel_scores_correct_for_its_own_case():
    assert (
        judge({"expects": "refusal"}, "-- INSUFFICIENT SCHEMA: x", None, None).outcome
        is Outcome.CORRECT
    )
    assert (
        judge({"expects": "out_of_scope"}, "-- OUT OF SCOPE: x", None, None).outcome
        is Outcome.CORRECT
    )


def test_refusing_an_answerable_question_is_caught():
    q = {"expects": "rows", "expected": {"rows": [[1]]}}
    verdict = judge(q, "-- INSUFFICIENT SCHEMA: giving up", None, None)
    assert verdict.outcome is Outcome.REFUSED_WRONGLY
    assert not verdict.outcome.is_silent_wrong


def test_disambiguation_is_held_for_human_review():
    verdict = judge({"expects": "disambiguation"}, "SELECT 1", None, None)
    assert verdict.outcome is Outcome.NEEDS_REVIEW


def test_needs_review_is_excluded_from_the_denominator():
    from pos_copilot.scoring import summarise

    items = [
        ({"id": "a", "view_covered": False}, Judgement(Outcome.CORRECT)),
        ({"id": "b", "view_covered": False}, Judgement(Outcome.NEEDS_REVIEW)),
    ]
    stats = summarise(items)
    assert stats["overall"]["n"] == 1, "an unscorable question must not count as a pass"
    assert stats["overall"]["needs_review"] == ["b"]


def test_accuracy_is_reported_three_ways():
    from pos_copilot.scoring import summarise

    items = [
        ({"id": "a", "view_covered": True}, Judgement(Outcome.CORRECT)),
        ({"id": "b", "view_covered": False}, Judgement(Outcome.WRONG_ROWS)),
    ]
    stats = summarise(items)
    assert set(stats) == {"overall", "view_covered", "not_view_covered"}
    assert stats["view_covered"]["n"] == 1
    assert stats["not_view_covered"]["correct"] == 0


def test_every_reported_accuracy_carries_n_and_an_interval():
    from pos_copilot.scoring import summarise

    stats = summarise(
        [({"id": "a", "view_covered": False}, Judgement(Outcome.CORRECT))]
    )
    assert "95% CI" in stats["overall"]["accuracy"]
    assert "(1/1" in stats["overall"]["accuracy"]


# ── The stub ─────────────────────────────────────────────────────────────────


def test_the_stub_needs_no_key_and_records_what_it_was_asked():
    stub = StubProvider(responses={"low on": "SELECT 1"})
    assert stub.generate("what are we low on") == "SELECT 1"
    assert stub.generate("something else").startswith("-- INSUFFICIENT SCHEMA")
    assert len(stub.calls) == 2


# ── Shape-aware comparison ───────────────────────────────────────────────────


def test_all_matching_ignores_row_order():
    verdict = compare({"rows": [[1], [2]]}, {"rows": [[2], [1]]}, "all_matching")
    assert verdict.outcome is Outcome.CORRECT


def test_all_matching_fails_on_over_fetching():
    """A loose predicate adds rows the reference does not have."""
    verdict = compare({"rows": [[1], [2]]}, {"rows": [[1], [2], [3]]}, "all_matching")
    assert verdict.outcome is Outcome.WRONG_ROWS
    assert "1 unexpected" in verdict.detail


def test_all_matching_fails_on_under_fetching():
    """An incomplete answer is a wrong answer, LIMIT clause or not."""
    verdict = compare({"rows": [[1], [2], [3]]}, {"rows": [[1], [2]]}, "all_matching")
    assert verdict.outcome is Outcome.WRONG_ROWS
    assert "1 missing" in verdict.detail


def test_ordered_shapes_still_care_about_order():
    for shape in ("top_n", "ranked_all", "scalar"):
        verdict = compare({"rows": [[1], [2]]}, {"rows": [[2], [1]]}, shape)
        assert verdict.outcome is Outcome.WRONG_ORDER, shape


def test_a_truncated_result_is_not_scored_as_a_wrong_answer():
    """The missing rows are unknowable, so comparison would be dishonest."""
    q = {"expects": "rows", "result_shape": "all_matching", "expected": {"rows": [[1]]}}
    execution = {
        "rows": [[1]],
        "row_count": 100,
        "truncated": True,
        "total_row_count": 440,
    }
    verdict = judge(q, "SELECT 1", execution, None)
    assert verdict.outcome is Outcome.EXECUTION_ERROR
    assert "440 matched" in verdict.detail


# ── The prompt freeze ────────────────────────────────────────────────────────


def test_the_prompt_matches_its_freeze_record():
    """The prompt is frozen for the duration of a measurement run.

    Editing any prompt or context file changes the fingerprint, invalidates
    every cached response, and restarts the measurement — at 20 requests per
    day that is days of elapsed time, not minutes. This test makes the freeze
    structural instead of a promise.

    Unfreezing is deliberate: edit the prompt, regenerate
    evals/PROMPT_FREEZE.json, and accept that the runs start over.
    """
    import json
    from pathlib import Path

    record = json.loads(
        (
            Path(__file__).resolve().parents[2] / "evals" / "PROMPT_FREEZE.json"
        ).read_text(encoding="utf-8")
    )
    bundle = load_sql_prompt()
    actual = bundle_fingerprint(bundle.hashes)

    changed = sorted(
        name
        for name, digest in bundle.hashes.items()
        if record["hashes"].get(name) != digest
    )
    assert actual == record["fingerprint"], (
        f"prompt changed since the freeze on {record['frozen_on']}: "
        f"{changed}. Every cached response is now invalid and the measurement "
        "restarts. If that is intended, regenerate evals/PROMPT_FREEZE.json."
    )
