"""Unit tests for the seed generator.

These assert; they do not measure (ADR-0005). Nothing here needs a database or
an API key.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

import pytest
import seed


def test_substream_is_stable_across_calls():
    a = [seed.substream("demand", 1, 42).random() for _ in range(5)]
    b = [seed.substream("demand", 1, 42).random() for _ in range(5)]
    assert a == b


def test_substream_is_independent_per_key():
    """Adding a product must not shift another product's history."""
    a = seed.substream("demand", 1, 100).random()
    b = seed.substream("demand", 1, 101).random()
    c = seed.substream("price", 1, 100).random()
    assert len({a, b, c}) == 3


def test_substream_does_not_use_salted_hash():
    """A hash()-derived seed would change between processes. sha256 does not.

    The expected value is pinned deliberately: if this changes, seed output
    changed with it and seed/CHECKSUMS.txt must be regenerated on purpose.
    """
    assert seed.substream("canary").randrange(10**9) == 688909735


def test_money_quantises_half_up():
    assert seed.money("1.005") == Decimal("1.01")
    assert seed.money("2.344") == Decimal("2.34")
    assert seed.money(3) == Decimal("3.00")
    assert str(seed.money("0.1")) == "0.10"


def test_poisson_is_non_negative_and_zero_for_zero_lambda():
    rng = seed.substream("test-poisson")
    assert seed.poisson(rng, 0.0) == 0
    assert seed.poisson(rng, -1.0) == 0
    draws = [seed.poisson(rng, 3.0) for _ in range(2000)]
    assert all(d >= 0 for d in draws)
    # Mean of a Poisson(3) sample of this size lands well inside these bounds.
    assert 2.7 < sum(draws) / len(draws) < 3.3


def test_poisson_is_reproducible():
    assert [seed.poisson(seed.substream("p", i), 2.5) for i in range(6)] == [
        seed.poisson(seed.substream("p", i), 2.5) for i in range(6)
    ]


def test_data_end_date_is_a_constant_not_wall_clock():
    assert seed.DATA_END_DATE.isoformat() == "2026-06-30"


def test_every_table_has_a_column_list():
    assert set(seed.TABLE_ORDER) == set(seed.COLUMNS)


def test_diwali_is_a_multi_week_ramp_not_a_single_day_spike():
    """The whole point of the Festival model.

    A single-day multiplier or a sinusoid cannot produce this shape, so assert
    the shape rather than any one value: elevated three weeks out, climbing
    monotonically into Dhanteras, and a slump on the far side.
    """
    factors = seed.build_day_factors(date(2025, 1, 1), date(2026, 6, 30), 1)

    three_weeks_out = factors[date(2025, 9, 29)]
    ten_days_out = factors[date(2025, 10, 8)]
    peak = factors[date(2025, 10, 17)]  # day before Dhanteras
    slump = factors[date(2025, 10, 25)]

    assert three_weeks_out > 1.0
    assert ten_days_out > three_weeks_out
    assert peak > ten_days_out
    assert peak > 2.5
    assert slump < 0.9

    # The build is genuinely weeks long, not a handful of days.
    elevated = [d for d, f in factors.items() if f > 1.3 and d.month == 10]
    assert len(elevated) >= 14


def test_holi_is_quiet_on_the_day_and_busy_before_it():
    factors = seed.build_day_factors(date(2025, 1, 1), date(2026, 6, 30), 1)
    assert factors[date(2026, 3, 4)] < 0.7
    assert factors[date(2026, 3, 3)] > 1.4


def test_regional_festivals_are_weighted_by_store():
    """Ganesh Chaturthi is a Maharashtra event; Pune should out-index Nagpur."""
    pune = seed.build_day_factors(date(2025, 1, 1), date(2026, 6, 30), 1)
    nagpur = seed.build_day_factors(date(2025, 1, 1), date(2026, 6, 30), 3)
    day = date(2025, 8, 26)
    assert pune[day] > nagpur[day] > 1.0


def test_overlapping_festivals_combine_by_max_not_by_product():
    """Four overlapping ramps multiplied together produce a fantasy number."""
    factors = seed.build_day_factors(date(2025, 1, 1), date(2026, 6, 30), 1)
    assert max(factors.values()) < 3.0


def test_seasonality_opposes_for_cold_and_hot_drinks():
    table = seed.build_seasonality()
    names = [c.name for c in seed.CATEGORY_DEFS]
    cold = table[names.index("Soft Drinks & Juices") + 1]
    hot = table[names.index("Tea & Coffee") + 1]
    peak_summer, midwinter = 150, 15
    assert cold[peak_summer] > cold[midwinter]
    assert hot[midwinter] > hot[peak_summer]


def test_sunday_outsells_saturday():
    table = seed.build_dow_factors()
    for row in table.values():
        assert row[6] >= row[5], "Sunday is the peak grocery day in this market"


def test_gst_rates_are_valid_slabs():
    slabs = {"0.00", "0.05", "0.12", "0.18", "0.28"}
    for cat in seed.CATEGORY_DEFS:
        assert cat.gst_rate in slabs, f"{cat.name} has slab {cat.gst_rate}"


def test_no_user_display_name_looks_like_a_person(tmp_path):
    """ADR-0002 forbids realistic employee names, including synthetic ones."""
    csvs = seed.CsvSet(tmp_path)
    try:
        stores = seed.build_stores(csvs, seed.SIZES["small"])
        seed.build_users(csvs, stores)
    finally:
        csvs.close()

    rows = list(csv.DictReader((tmp_path / "005_users.csv").open(encoding="utf-8")))
    assert rows
    for row in rows:
        assert row["display_name"].split()[0] in {"Owner", "Manager", "Clerk"}


@pytest.mark.parametrize("size", ["small", "full"])
def test_size_specs_end_on_the_anchor(size):
    spec = seed.SIZES[size]
    assert spec.days > 0
    assert spec.store_count >= 1


def test_generation_is_deterministic_within_a_platform(tmp_path):
    """Generate twice and compare.

    This catches genuine non-determinism — a uuid4, a set iteration, a
    date.today(). It deliberately does NOT compare against the committed
    seed/CHECKSUMS.txt, because that claim is scoped to the pinned
    python:3.12-slim image and this test runs on whatever Python is to hand.
    `make verify-seed`, which CI runs inside the pinned image, is what asserts
    the cross-machine claim.
    """
    spec = seed.SIZES["small"]
    hashes = []
    for run in ("a", "b"):
        out = tmp_path / run
        csvs = seed.CsvSet(out)
        try:
            summary = seed.simulate(csvs, spec)
        finally:
            csvs.close()
        hashes.append(seed.write_manifest(out, spec, csvs, summary))
    assert hashes[0] == hashes[1]
    assert len(hashes[0]) == len(seed.TABLE_ORDER)
