"""The interval that ADR-0001's threshold 2 is read against."""

from __future__ import annotations

import pytest
from wilson import decides, summarise, wilson


def test_the_worked_example_in_adr_0001():
    """25/30 is 83.3% with a 95% CI of 66-93%. The ADR quotes this; pin it."""
    assert summarise(25, 30) == "83.3% (25/30, 95% CI 66-93%)"


def test_the_adr_example_cannot_decide_the_85_percent_question():
    """The point estimate reads 'below 85'. The interval says 'do not act'."""
    assert 25 / 30 < 0.85
    assert decides(25, 30, 0.85) == "inconclusive"


def test_growing_the_set_to_fifty_does_not_rescue_it():
    """ADR-0001 declines to pre-emptively grow the eval set on these grounds."""
    assert summarise(42, 50) == "84.0% (42/50, 95% CI 71-92%)"
    assert decides(42, 50, 0.85) == "inconclusive"


def test_a_clear_failure_is_still_called():
    """An interval that excludes the line decides, and must be allowed to."""
    assert decides(20, 40, 0.85) == "below"


def test_a_clear_pass_is_still_called():
    assert decides(40, 40, 0.85) == "above"


def test_bounds_stay_inside_zero_and_one():
    """Where the normal approximation misbehaves and Wilson does not."""
    for successes, n in ((0, 10), (10, 10), (1, 100), (99, 100)):
        low, high = wilson(successes, n)
        assert 0.0 <= low <= high <= 1.0


def test_interval_narrows_as_n_grows():
    widths = [wilson(round(0.85 * n), n) for n in (20, 50, 200, 1000)]
    spans = [high - low for low, high in widths]
    assert spans == sorted(spans, reverse=True)


def test_several_hundred_questions_needed_to_resolve_five_points():
    """The claim ADR-0001 makes for declining to grow the set."""
    low, high = wilson(round(0.85 * 400), 400)
    assert high - low < 0.08
    low, high = wilson(round(0.85 * 50), 50)
    assert high - low > 0.18


def test_rejects_impossible_inputs():
    with pytest.raises(ValueError):
        wilson(5, 0)
    with pytest.raises(ValueError):
        wilson(11, 10)
