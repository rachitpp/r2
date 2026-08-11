"""Blank means unset.

This is not a hypothetical. `export LIVE_MAX_CALLS` in the Makefile exports it
as an empty string when nobody set it, and the first version of the live path
read it with `int(os.environ.get("LIVE_MAX_CALLS", "50"))` — which raised
`ValueError` on every request, from a variable no one had touched. The default
has to cover blank as well as missing, and these tests are the known-positive
for that.
"""

from __future__ import annotations

import pytest

from pos_copilot import env


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_variable_exported_with_no_value_takes_the_default(blank, monkeypatch):
    monkeypatch.setenv("R2_TEST_VALUE", blank)
    assert env.text("R2_TEST_VALUE", "fallback") == "fallback"
    assert env.integer("R2_TEST_VALUE", 50) == 50
    assert env.number("R2_TEST_VALUE", 1.5) == 1.5


def test_a_missing_variable_takes_the_default(monkeypatch):
    monkeypatch.delenv("R2_TEST_VALUE", raising=False)
    assert env.text("R2_TEST_VALUE", "fallback") == "fallback"
    assert env.integer("R2_TEST_VALUE", 50) == 50


def test_a_set_variable_wins_and_is_stripped(monkeypatch):
    monkeypatch.setenv("R2_TEST_VALUE", "  7  ")
    assert env.text("R2_TEST_VALUE", "fallback") == "7"
    assert env.integer("R2_TEST_VALUE", 50) == 7
    assert env.number("R2_TEST_VALUE", 1.5) == 7.0


def test_a_value_that_is_not_a_number_still_raises(monkeypatch):
    """Blank is a missing setting; `banana` is a typo someone should see."""
    monkeypatch.setenv("R2_TEST_VALUE", "banana")
    with pytest.raises(ValueError):
        env.integer("R2_TEST_VALUE", 50)
