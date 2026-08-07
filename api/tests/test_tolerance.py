"""Tolerance, and the guarantee that it never swallows a trap.

The tolerances are absolute and small on purpose. This file exists to keep them
that way: if one ever grows to within an order of magnitude of a real trap's
gap, the trap silently stops being a trap and the eval reports a pass on the
failure it was built to catch.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pos_copilot.tolerance import (
    MONEY,
    RATE,
    Kind,
    classify,
    numbers_match,
    values_match,
)

# The right answer and the known wrong answer for each trap, measured against
# the seeded database during the cross-check. Rate figures are percentage
# points, matching how the eval reports them.
TRAP_GAPS = {
    "returns: net vs gross units (q007/q009)": (54594, 54759, Kind.EXACT),
    "GST: pre-reform vs blended across 22 Sep (q018/q019)": (
        Decimal("8.23"),
        Decimal("7.50"),
        Kind.RATE,
    ),
    "GST: post-reform vs blended (q018/q019)": (
        Decimal("6.73"),
        Decimal("7.50"),
        Kind.RATE,
    ),
    "GST: September is itself a blend": (
        Decimal("8.23"),
        Decimal("7.67"),
        Kind.RATE,
    ),
    "velocity: stockout-corrected vs naive /30 (q010/q012)": (
        Decimal("1.636"),
        Decimal("1.200"),
        Kind.RATE,
    ),
    "velocity: second case": (Decimal("5.227"), Decimal("3.833"), Kind.RATE),
    "store size confound: uplift Pune vs Nagpur (q027)": (
        Decimal("1.674"),
        Decimal("1.619"),
        Kind.RATE,
    ),
}


@pytest.mark.parametrize("label", sorted(TRAP_GAPS))
def test_tolerance_stays_an_order_of_magnitude_below_every_trap_gap(label):
    right, wrong, kind = TRAP_GAPS[label]
    gap = abs(Decimal(str(right)) - Decimal(str(wrong)))
    tol = {Kind.EXACT: Decimal("0"), Kind.MONEY: MONEY, Kind.RATE: RATE}[kind]

    if tol == 0:
        assert gap > 0, f"{label}: exact comparison, but the values are equal"
        return

    assert gap > tol * 10, (
        f"{label}: the gap between right ({right}) and wrong ({wrong}) is "
        f"{gap}, which is not an order of magnitude above the {kind} tolerance "
        f"of {tol}. Either tighten the tolerance or the trap is no longer a "
        f"trap — the eval would score the wrong answer as correct."
    )


@pytest.mark.parametrize("label", sorted(TRAP_GAPS))
def test_every_trap_actually_fails_comparison(label):
    """The gap arithmetic above is necessary but not sufficient."""
    right, wrong, kind = TRAP_GAPS[label]
    assert not values_match(right, wrong, kind), (
        f"{label}: the wrong answer compares EQUAL to the right one"
    )


def test_the_returns_trap_would_die_under_any_relative_tolerance():
    """Why the spec says absolute, never relative.

    54,759 against 54,594 is a 0.3% difference. A 1% relative tolerance — a
    modest-sounding choice — reports the gross figure as the net one.
    """
    net, gross = Decimal("54594"), Decimal("54759")
    relative = abs(gross - net) / net
    assert relative < Decimal("0.01")
    assert not values_match(net, gross, Kind.EXACT)


# ── Classification ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("units", Kind.EXACT),
        ("net_units", Kind.EXACT),
        ("product_id", Kind.EXACT),
        ("on_hand", Kind.EXACT),
        ("net_revenue", Kind.MONEY),
        ("unit_cost", Kind.MONEY),
        ("subtotal", Kind.MONEY),
        ("min_order_value", Kind.MONEY),
        ("effective_rate_pct", Kind.RATE),
        ("margin_pct", Kind.RATE),
        ("units_per_day", Kind.RATE),
        ("days_of_cover", Kind.RATE),
        ("uplift_vs_own_baseline", Kind.RATE),
    ],
)
def test_columns_classify_to_the_right_tolerance(column, expected):
    assert classify(column, 1) is expected


def test_a_rate_hint_beats_a_money_hint():
    """margin is money; margin_pct is a rate. Order of checks matters."""
    assert classify("margin", 1) is Kind.MONEY
    assert classify("margin_pct", 1) is Kind.RATE


def test_dates_are_compared_as_days_not_strings():
    assert classify("effective_from", "2025-03-15") is Kind.DATE
    assert values_match("2025-03-15", "2025-03-15T00:00:00+05:30", Kind.DATE)
    assert values_match("2025-03-15", "2025-03-15 00:00:00", Kind.DATE)
    assert not values_match("2025-03-15", "2025-03-16", Kind.DATE)


def test_booleans_survive_any_rendering():
    for rendering in (True, "true", "t", "TRUE", " True "):
        assert values_match(True, rendering, Kind.TEXT)
    assert not values_match(True, "false", Kind.TEXT)


def test_padded_to_char_output_matches_its_trimmed_form():
    assert values_match("Sunday   ", "Sunday", Kind.TEXT)


# ── Precision alignment ──────────────────────────────────────────────────────


def test_a_rounded_reference_matches_an_unrounded_answer():
    """q033: round(avg(...)) = 326958 against a raw avg of 326958.0876."""
    assert numbers_match(Decimal("326958"), Decimal("326958.0876"), Kind.MONEY)


def test_precision_alignment_does_not_forgive_a_real_error():
    """It aligns decimals, not significant figures."""
    assert not numbers_match(Decimal("1234.56"), Decimal("1200"), Kind.MONEY)
    assert not numbers_match(Decimal("326958"), Decimal("326000"), Kind.MONEY)


def test_money_tolerance_is_one_paisa():
    assert numbers_match(Decimal("10.00"), Decimal("10.01"), Kind.MONEY)
    assert not numbers_match(Decimal("10.00"), Decimal("10.02"), Kind.MONEY)


def test_rate_tolerance_is_half_a_hundredth():
    assert numbers_match(Decimal("8.230"), Decimal("8.234"), Kind.RATE)
    assert not numbers_match(Decimal("8.230"), Decimal("8.240"), Kind.RATE)


def test_counts_admit_no_tolerance_at_all():
    assert numbers_match(Decimal("100"), Decimal("100"), Kind.EXACT)
    assert not numbers_match(Decimal("100"), Decimal("101"), Kind.EXACT)
