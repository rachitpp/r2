"""Invariants the seeded database must satisfy.

Skipped when TEST_DATABASE_URL is unset. These are assertions, not
measurements: each one is a property that is either true or the seed is wrong.
"""

from __future__ import annotations

import pytest
from conftest import fetch_all, fetch_one

pytestmark = pytest.mark.db


def test_stock_on_hand_matches_the_movement_history(conn):
    """on_hand = sum(movements) - sum(sale_lines), for every row of inventory.

    This is what makes on_hand a materialisation of history rather than a
    number the generator asserted.
    """
    checked, violations = fetch_one(
        conn,
        """
        WITH mv AS (
            SELECT store_id, product_id, sum(quantity) AS moved
            FROM inventory_movements GROUP BY 1, 2),
        sl AS (
            SELECT store_id, product_id, sum(quantity) AS sold
            FROM sale_lines GROUP BY 1, 2)
        SELECT count(*),
               count(*) FILTER (
                   WHERE i.on_hand
                         <> coalesce(mv.moved, 0) - coalesce(sl.sold, 0))
        FROM inventory i
        LEFT JOIN mv USING (store_id, product_id)
        LEFT JOIN sl USING (store_id, product_id)
        """,
    )
    assert checked > 0
    assert violations == 0


def test_no_supplier_has_two_sets_of_terms_in_force(conn):
    """The exclusion constraint should make this impossible; check it anyway."""
    (worst,) = fetch_one(
        conn,
        """
        SELECT coalesce(max(n), 0) FROM (
            SELECT count(*) AS n FROM supplier_terms
            WHERE valid_period @> DATE '2026-06-30'
            GROUP BY supplier_id) t
        """,
    )
    assert worst <= 1


def test_current_terms_and_prices_are_actually_in_force(conn):
    """A row with effective_to IS NULL must not start in the future.

    Without this the table looks right and every answer is wrong: the terms
    genuinely in force throughout the data would be the superseded ones.
    """
    for table in ("supplier_terms", "supplier_prices"):
        (future,) = fetch_one(
            conn,
            f"SELECT count(*) FROM {table} "
            "WHERE effective_to IS NULL AND effective_from > DATE '2026-06-30'",
        )
        assert future == 0, f"{table} has {future} current rows starting in the future"


def test_every_supplier_has_terms_in_force_on_the_anchor_date(conn):
    missing = fetch_all(
        conn,
        """
        SELECT s.code FROM suppliers s
        WHERE NOT EXISTS (
            SELECT 1 FROM supplier_terms t
            WHERE t.supplier_id = s.supplier_id
              AND t.valid_period @> DATE '2026-06-30')
        ORDER BY s.code
        """,
    )
    assert missing == []


def test_supplier_terms_have_a_supersession_chain(conn):
    """Beat 2 asks what the terms were BEFORE the renegotiation."""
    (with_history,) = fetch_one(
        conn, "SELECT count(*) FROM supplier_terms WHERE supersedes_id IS NOT NULL"
    )
    assert with_history > 0


def test_denormalised_columns_on_sale_lines_match_the_header(conn):
    """Guaranteed by the composite foreign key; asserted so the guarantee is
    visible to anyone reading the tests rather than only the DDL."""
    (mismatched,) = fetch_one(
        conn,
        """
        SELECT count(*) FROM sale_lines sl JOIN sales s USING (sale_id)
        WHERE sl.store_id <> s.store_id OR sl.business_date <> s.business_date
        """,
    )
    assert mismatched == 0


def test_returns_are_the_only_negative_quantities(conn):
    (bad,) = fetch_one(
        conn,
        """
        SELECT count(*) FROM sale_lines sl JOIN sales s USING (sale_id)
        WHERE (sl.quantity < 0) <> (s.sale_type = 'return')
        """,
    )
    assert bad == 0


def test_the_data_ends_on_the_anchor_date(conn):
    (last,) = fetch_one(conn, "SELECT max(business_date) FROM sale_lines")
    assert last.isoformat() == "2026-06-30", (
        "seed data must end on DATA_END_DATE; AS_OF_DATE depends on it"
    )


def test_daily_rollup_agrees_with_the_line_items(conn):
    (units, rollup) = fetch_one(
        conn,
        """
        SELECT (SELECT sum(quantity) FROM sale_lines),
               (SELECT sum(net_units) FROM daily_product_sales)
        """,
    )
    assert units == rollup


def test_velocity_excludes_stockout_days_from_the_denominator(conn):
    (rows,) = fetch_one(
        conn,
        "SELECT count(*) FROM v_product_velocity_30d WHERE available_days_30d < 30",
    )
    assert rows > 0, "no product stocked out — the stockout trap is untested"


def test_beat_one_returns_a_usable_answer(conn):
    """'What are we low on that sells fastest?' must be one query, no heroics."""
    rows = fetch_all(
        conn,
        """
        SELECT sku, on_hand, units_per_day, days_of_cover
        FROM v_stock_status
        WHERE store_id = 1 AND below_reorder_point AND on_hand > 0
        ORDER BY days_of_cover, units_per_day DESC, sku
        LIMIT 10
        """,
    )
    assert len(rows) == 10
    covers = [r[3] for r in rows]
    assert covers == sorted(covers)
    assert all(r[2] > 0 for r in rows)


def test_readonly_role_cannot_reach_staff_identities(conn):
    """ADR-0002's pattern-not-people constraint, enforced by grants."""
    reachable = fetch_all(
        conn,
        """
        SELECT table_name FROM information_schema.table_privileges
        WHERE grantee = 'pos_readonly'
          AND table_name IN ('users', 'sale_operators')
        """,
    )
    assert reachable == []


def test_readonly_role_is_forced_read_only_and_time_limited(conn):
    (config,) = fetch_one(
        conn, "SELECT rolconfig FROM pg_roles WHERE rolname = 'pos_readonly'"
    )
    settings = dict(item.split("=", 1) for item in config)
    assert settings["default_transaction_read_only"] == "on"
    assert settings["statement_timeout"] == "5s"


def test_gst_rates_have_no_overlapping_periods(conn):
    """The exclusion constraint should make this impossible; check it anyway."""
    (worst,) = fetch_one(
        conn,
        """
        SELECT coalesce(max(n), 0) FROM (
            SELECT count(*) AS n FROM gst_rates
            WHERE valid_period @> DATE '2026-06-30'
            GROUP BY category_id) t
        """,
    )
    assert worst == 1


def test_every_category_has_a_rate_on_both_sides_of_the_reform(conn):
    """A gap here would silently untax part of the history."""
    for probe in ("2025-09-21", "2025-09-22", "2026-06-30"):
        (uncovered,) = fetch_one(
            conn,
            f"""
            SELECT count(*) FROM categories c
            WHERE NOT EXISTS (
                SELECT 1 FROM gst_rates g
                WHERE g.category_id = c.category_id
                  AND g.valid_period @> DATE '{probe}')
            """,
        )
        assert uncovered == 0, f"{uncovered} categories have no GST rate on {probe}"


def test_the_reform_removed_the_12_and_28_slabs(conn):
    before = {
        r[0]
        for r in fetch_all(
            conn,
            "SELECT DISTINCT rate_pct FROM gst_rates WHERE effective_to IS NOT NULL",
        )
    }
    after = {
        r[0]
        for r in fetch_all(
            conn, "SELECT DISTINCT rate_pct FROM gst_rates WHERE effective_to IS NULL"
        )
    }
    assert {int(r) for r in before} == {0, 5, 12, 18, 28}
    assert {int(r) for r in after} == {0, 5, 18, 40}


def test_aerated_drinks_moved_to_the_40_percent_slab(conn):
    rows = fetch_all(
        conn,
        """
        SELECT g.rate_pct FROM gst_rates g JOIN categories c USING (category_id)
        WHERE c.name = 'Soft Drinks & Juices'
        ORDER BY g.effective_from
        """,
    )
    assert [int(r[0]) for r in rows] == [28, 40]


def test_tax_charged_matches_the_rate_in_force_on_the_day(conn):
    """The seed must have taxed each sale at its own date's rate, not today's.

    Checked at the line level either side of the reform: if the generator had
    used a single rate, one of these two would be wrong.
    """
    for probe, expected in (("2025-08-15", 28), ("2025-10-15", 40)):
        (charged,) = fetch_one(
            conn,
            f"""
            SELECT round(100.0 * sum(sl.quantity * sl.unit_price * g.rate_pct / 100)
                         / NULLIF(sum(sl.line_total), 0))
            FROM sale_lines sl
            JOIN products p USING (product_id)
            JOIN categories c USING (category_id)
            JOIN gst_rates g ON g.category_id = c.category_id
                            AND g.valid_period @> sl.business_date
            WHERE c.name = 'Soft Drinks & Juices'
              AND sl.business_date = DATE '{probe}'
            """,
        )
        assert int(charged) == expected


def test_the_reform_moved_the_effective_tax_rate(conn):
    """The trap has to be real, or the eval question testing it is theatre."""
    (before, after) = fetch_one(
        conn,
        """
        WITH era AS (
            SELECT business_date >= DATE '2025-09-22' AS post, subtotal, tax_total
            FROM sales
            WHERE business_date BETWEEN DATE '2025-07-01' AND DATE '2025-11-30'
        )
        SELECT
          round(100.0 * sum(tax_total) FILTER (WHERE NOT post)
                / NULLIF(sum(subtotal) FILTER (WHERE NOT post), 0), 2),
          round(100.0 * sum(tax_total) FILTER (WHERE post)
                / NULLIF(sum(subtotal) FILTER (WHERE post), 0), 2)
        FROM era
        """,
    )
    assert before > after
    assert before - after > 1.0, "the reform should be plainly visible, not marginal"


def test_only_one_diwali_in_the_window(conn):
    """Festival year-on-year is impossible for Diwali and must stay that way."""
    (last,) = fetch_one(conn, "SELECT max(business_date) FROM sale_lines")
    assert last.isoformat() == "2026-06-30"
    # Dhanteras 2026 is 6 November — past the end of the data.
    assert last < __import__("datetime").date(2026, 11, 6)
