"""The LIMIT wrapper and the guards around generated SQL.

CLAUDE.md rule 4. The prompt asks the model for a single SELECT with a LIMIT;
this is what happens when it does not comply, whether by accident or because
something in a document persuaded it otherwise.
"""

from __future__ import annotations

import os

import pytest

from pos_copilot.readonly_sql import (
    DEFAULT_MAX_ROWS,
    HARD_MAX_ROWS,
    UnsafeQuery,
    check,
    execute,
    guard,
    statement_count,
    strip_sql,
)

SAFE = "SELECT sku, on_hand FROM inventory ORDER BY sku"


# ── The bounding subquery ────────────────────────────────────────────────────


def test_a_limit_is_added_when_the_model_omits_one():
    assert "LIMIT 101" in guard(SAFE).sql
    assert guard(SAFE).max_rows == 100


def test_our_limit_binds_even_when_the_model_asks_for_more():
    """The wrapper caps the outer result regardless of the inner LIMIT.

    The wrapper selects max_rows + 1; the extra row is a truncation probe and
    is never returned. The enforced cap on returned data is still max_rows.
    """
    guarded = guard("SELECT * FROM sale_lines LIMIT 500000", max_rows=25)
    assert guarded.sql.endswith("LIMIT 26")
    assert guarded.max_rows == 25
    assert "LIMIT 500000" in guarded.sql  # inner query untouched, outer caps it


def test_max_rows_cannot_exceed_the_hard_ceiling():
    assert guard(SAFE, max_rows=10**6).max_rows == HARD_MAX_ROWS


def test_max_rows_must_be_positive():
    with pytest.raises(ValueError):
        guard(SAFE, max_rows=0)


def test_default_matches_the_prompt_and_env_default():
    assert DEFAULT_MAX_ROWS == 100


def test_a_trailing_semicolon_is_tolerated():
    assert "LIMIT" in guard("SELECT 1;").sql


# ── Rejecting what is not a single read-only SELECT ──────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sales",
        "UPDATE inventory SET on_hand = 0",
        "INSERT INTO sales (sale_id) VALUES (1)",
        "DROP TABLE sales",
        "TRUNCATE sale_lines",
        "GRANT SELECT ON users TO pos_readonly",
        "ALTER TABLE sales ADD COLUMN x int",
        "CREATE TABLE evil (id int)",
        "SET default_transaction_read_only = off",
        "COPY sales TO '/tmp/out.csv'",
        "REFRESH MATERIALIZED VIEW daily_product_sales",
    ],
)
def test_writes_and_ddl_are_refused(sql):
    with pytest.raises(UnsafeQuery):
        check(sql)


def test_a_second_statement_is_refused():
    with pytest.raises(UnsafeQuery, match="one statement"):
        check("SELECT 1; DROP TABLE sales")


def test_a_data_modifying_cte_is_refused():
    """Starts with WITH, is a write. A leading-token check alone misses it."""
    with pytest.raises(UnsafeQuery, match="delete"):
        check(
            "WITH gone AS (DELETE FROM sale_lines RETURNING *) "
            "SELECT count(*) FROM gone"
        )


def test_an_empty_query_is_refused():
    for sql in ("", "   ", "-- just a comment"):
        with pytest.raises(UnsafeQuery):
            check(sql)


# ── The scanner: literals and comments must not fool the statement count ─────


def test_a_semicolon_inside_a_string_is_not_a_statement_break():
    """Otherwise a legitimate query gets refused for looking like two."""
    sql = "SELECT * FROM products WHERE name = 'a; b' ORDER BY sku"
    assert statement_count(strip_sql(sql)) == 1
    check(sql)


def test_a_keyword_inside_a_string_is_not_a_write():
    check("SELECT * FROM products WHERE name = 'DROP TABLE sales' ORDER BY sku")


def test_a_comment_cannot_hide_a_second_statement():
    """`--` ends at the newline; what follows it is real SQL again."""
    with pytest.raises(UnsafeQuery):
        check("SELECT 1 -- harmless\n; DROP TABLE sales")


def test_a_block_comment_cannot_smuggle_a_statement():
    check("SELECT /* ; DROP TABLE sales ; */ sku FROM products ORDER BY sku")


def test_nested_block_comments_terminate_correctly():
    check("SELECT /* a /* b */ c */ sku FROM products ORDER BY sku")


def test_dollar_quoting_is_understood():
    sql = "SELECT $tag$ ; DROP TABLE sales ; $tag$ AS x"
    assert statement_count(strip_sql(sql)) == 1


def test_escaped_quotes_do_not_end_the_literal_early():
    sql = "SELECT * FROM products WHERE name = 'it''s; fine' ORDER BY sku"
    assert statement_count(strip_sql(sql)) == 1
    check(sql)


def test_stripping_preserves_token_boundaries():
    """Deleting a literal outright would fuse SELECT and FROM into one token,
    which would then read as an unrecognised leading keyword."""
    assert strip_sql("SELECT'a'FROM t").split() == ["SELECT", "FROM", "t"]


# ── Against the live read-only role ──────────────────────────────────────────

pytestmark_db = pytest.mark.db


@pytest.fixture(scope="module")
def readonly_conn():
    url = os.environ.get("TEST_READONLY_URL")
    if not url:
        pytest.skip("TEST_READONLY_URL is not set")
    psycopg = pytest.importorskip("psycopg")
    conn = psycopg.connect(url)
    yield conn
    conn.close()


@pytest.mark.db
def test_the_limit_actually_binds_against_the_database(readonly_conn):
    result = execute(readonly_conn, "SELECT sale_line_id FROM sale_lines", max_rows=7)
    assert result["row_count"] == 7
    assert result["truncated"] is True
    assert result["columns"] == ["sale_line_id"]


@pytest.mark.db
def test_a_query_returning_less_than_the_cap_is_not_truncated(readonly_conn):
    result = execute(readonly_conn, "SELECT 1 AS one", max_rows=50)
    assert result["row_count"] == 1
    assert result["truncated"] is False


@pytest.mark.db
def test_the_role_itself_refuses_writes_even_if_the_guard_were_bypassed(
    readonly_conn,
):
    """Defence in depth: the guard is layer one, the role is the backstop."""
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        readonly_conn.execute("CREATE TABLE should_not_exist (id int)")
    readonly_conn.rollback()


@pytest.mark.db
def test_the_role_cannot_read_staff_identities(readonly_conn):
    """ADR-0002, enforced by grants rather than by the guard."""
    psycopg = pytest.importorskip("psycopg")
    for table in ("users", "sale_operators"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            readonly_conn.execute(f"SELECT * FROM {table} LIMIT 1")
        readonly_conn.rollback()


# ── The scope tripwire ───────────────────────────────────────────────────────


def test_the_tripwire_catches_a_result_leaking_another_store():
    """Reaching this means the generated SQL was missing its scope predicate."""
    from pos_copilot.readonly_sql import ScopeViolation, check_scope

    result = {"columns": ["store_id", "sku"], "rows": [[1, "a"], [3, "b"]]}
    with pytest.raises(ScopeViolation, match=r"store_id \[3\]"):
        check_scope(result, {1})


def test_the_tripwire_passes_a_correctly_scoped_result():
    from pos_copilot.readonly_sql import check_scope

    check_scope({"columns": ["store_id", "sku"], "rows": [[1, "a"], [1, "b"]]}, {1})


def test_the_tripwire_does_not_filter_it_refuses():
    """Dropping the offending rows would hide the defect. Rule 5 forbids it."""
    from pos_copilot.readonly_sql import ScopeViolation, check_scope

    result = {"columns": ["store_id"], "rows": [[1], [2]]}
    with pytest.raises(ScopeViolation):
        check_scope(result, {1})
    assert result["rows"] == [[1], [2]], "rows must be left untouched"


def test_the_tripwire_is_inert_for_an_unscoped_user():
    from pos_copilot.readonly_sql import check_scope

    check_scope({"columns": ["store_id"], "rows": [[1], [2], [3]]}, None)


def test_the_tripwire_cannot_check_a_result_with_no_store_id():
    """A known limit: an aggregate that drops store_id is unverifiable here.

    That is why this is a backstop and the WHERE clause is the mechanism.
    """
    from pos_copilot.readonly_sql import check_scope

    check_scope({"columns": ["total"], "rows": [[42]]}, {1})


@pytest.mark.db
def test_the_tripwire_fires_against_the_real_database(readonly_conn):
    from pos_copilot.readonly_sql import ScopeViolation

    execute(
        readonly_conn,
        "SELECT store_id, product_id FROM inventory WHERE store_id = 1",
        max_rows=5,
        visible_store_ids={1},
    )
    with pytest.raises(ScopeViolation):
        execute(
            readonly_conn,
            "SELECT store_id, product_id FROM inventory ORDER BY store_id DESC",
            max_rows=5,
            visible_store_ids={1},
        )


# ── Ties the question does not break ─────────────────────────────────────────


def _judge(expected, got_rows, shape="top_n"):
    from pos_copilot.scoring import compare

    return compare(expected, {"rows": got_rows}, shape)


def test_rows_tied_inside_the_answer_may_come_back_in_any_order():
    """The reference's `sku` tiebreak makes its query deterministic. It does not
    make the question determinate."""
    from pos_copilot.scoring import Outcome

    expected = {
        "columns": ["sku", "units"],
        "rows": [["A", 9], ["B", 5], ["C", 5]],
        "tie_keys": [9, 5, 5],
        "tie_pool": [],
    }
    assert _judge(expected, [["A", 9], ["C", 5], ["B", 5]]).outcome is Outcome.CORRECT


def test_a_contested_cut_may_be_filled_from_the_tied_pool():
    """q042 has five of ten slots contested among thirteen tied products."""
    from pos_copilot.scoring import Outcome

    expected = {
        "columns": ["sku", "units"],
        "rows": [["A", 9], ["B", 5]],
        "tie_keys": [9, 5],
        "tie_pool": [["B", 5], ["C", 5], ["D", 5]],
    }
    assert _judge(expected, [["A", 9], ["D", 5]]).outcome is Outcome.CORRECT


def test_a_row_from_outside_the_tie_is_still_wrong():
    """Relaxing ties must not relax anything else."""
    from pos_copilot.scoring import Outcome

    expected = {
        "columns": ["sku", "units"],
        "rows": [["A", 9], ["B", 5]],
        "tie_keys": [9, 5],
        "tie_pool": [["B", 5], ["C", 5]],
    }
    assert _judge(expected, [["A", 9], ["Z", 1]]).outcome is not Outcome.CORRECT


def test_the_settled_part_of_the_ranking_is_still_ordered_exactly():
    from pos_copilot.scoring import Outcome

    expected = {
        "columns": ["sku", "units"],
        "rows": [["A", 9], ["B", 7], ["C", 5], ["D", 5]],
        "tie_keys": [9, 7, 5, 5],
        "tie_pool": [],
    }
    # A and B are not tied — swapping them is a real ordering error.
    assert (
        _judge(expected, [["B", 7], ["A", 9], ["C", 5], ["D", 5]]).outcome
        is not Outcome.CORRECT
    )
