"""Guarded execution of generated SQL.

CLAUDE.md rule 4: generated SQL runs as the read-only role, and the row LIMIT
is enforced here — not by the database. Postgres has no max-rows setting, so
the role cannot provide one. What the role does provide is
`default_transaction_read_only`, a statement timeout, and no grant on the
tables holding staff identities.

This module is the other half. Four layers, because the prompt asking politely
for a LIMIT is not enforcement:

  1. **Reject anything that is not a single SELECT.** Statement count is
     checked by a scanner that understands string literals, dollar-quoting and
     comments, so a semicolon inside a string does not read as a statement
     break and a `--` comment cannot hide one.
  2. **Reject write and DDL keywords** at statement level, including the ones
     that arrive inside a CTE (`WITH x AS (DELETE ... RETURNING ...)` is a
     write that begins with WITH).
  3. **Wrap in a bounding subquery**: `SELECT * FROM (<sql>) _guarded LIMIT n`.
     This caps the rows even when the model omitted a LIMIT, and it caps them
     even when the model's own LIMIT is larger than ours.
  4. **Fetch through a named server-side cursor** with a capped itersize, so a
     query whose plan explodes cannot stream unbounded rows into the process
     before the LIMIT is applied.

Layer 3 alone would be enough for well-formed SQL. Layer 4 is there because
"well-formed" is the assumption under test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MAX_ROWS = 100
HARD_MAX_ROWS = 1000

# Checked against the first significant token and against every token that
# could start a statement. Read-only-looking wrappers (WITH, SELECT) are
# allowed through here and re-checked for embedded writes below.
FORBIDDEN = frozenset(
    {
        "insert",
        "update",
        "delete",
        "truncate",
        "drop",
        "create",
        "alter",
        "grant",
        "revoke",
        "comment",
        "copy",
        "vacuum",
        "analyze",
        "cluster",
        "reindex",
        "refresh",
        "call",
        "do",
        "execute",
        "prepare",
        "declare",
        "listen",
        "notify",
        "lock",
        "set",
        "reset",
        "begin",
        "commit",
        "rollback",
        "savepoint",
        "security",
        "import",
        "merge",
    }
)

ALLOWED_LEADING = frozenset({"select", "with", "table", "values"})


class UnsafeQuery(ValueError):
    """The generated SQL was refused before it reached the database."""


@dataclass(frozen=True)
class GuardedQuery:
    sql: str
    max_rows: int
    original: str = field(repr=False)


def strip_sql(sql: str) -> str:
    """Remove comments and string/identifier literals, preserving structure.

    Everything removed is replaced by a space rather than deleted, so token
    boundaries survive and `SELECT'a'FROM` cannot become `SELECTFROM`.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]

        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
            continue

        if ch == "/" and sql.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            out.append(" ")
            continue

        if ch in "'\"":
            quote, i = ch, i + 1
            while i < n:
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue

        if ch == "$":
            tag = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if tag:
                marker = tag.group(0)
                end = sql.find(marker, i + len(marker))
                i = n if end == -1 else end + len(marker)
                out.append(" ")
                continue

        out.append(ch)
        i += 1
    return "".join(out)


def statement_count(stripped: str) -> int:
    """Statements in SQL that has already had literals and comments removed."""
    return len([part for part in stripped.split(";") if part.strip()])


def check(sql: str) -> None:
    """Raise UnsafeQuery unless this is a single, read-only SELECT."""
    if not sql or not sql.strip():
        raise UnsafeQuery("empty query")

    stripped = strip_sql(sql)

    if statement_count(stripped) != 1:
        raise UnsafeQuery(
            "expected exactly one statement; "
            f"found {statement_count(stripped)}. Generated SQL must be a "
            "single SELECT."
        )

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped.lower())
    if not tokens:
        raise UnsafeQuery("no SQL found once comments and literals were removed")

    if tokens[0] not in ALLOWED_LEADING:
        raise UnsafeQuery(
            f"query starts with '{tokens[0]}'; only SELECT (or a WITH that "
            "resolves to one) may run under the read-only role"
        )

    # A data-modifying CTE is a write that begins with WITH, so leading-token
    # checks alone do not catch it.
    forbidden = sorted(FORBIDDEN.intersection(tokens))
    if forbidden:
        raise UnsafeQuery(
            f"query contains {', '.join(forbidden)}, which cannot appear in "
            "generated SQL even inside a CTE"
        )


def guard(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> GuardedQuery:
    """Validate and wrap. The returned SQL is what should be executed."""
    if max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    max_rows = min(max_rows, HARD_MAX_ROWS)

    check(sql)
    body = sql.strip().rstrip(";").strip()

    # The bounding subquery caps rows regardless of what the inner query says.
    # An inner LIMIT larger than ours is overridden; a smaller one still wins,
    # which is correct — the model asking for fewer rows is not a problem.
    wrapped = f"SELECT * FROM (\n{body}\n) AS _guarded LIMIT {max_rows}"
    return GuardedQuery(sql=wrapped, max_rows=max_rows, original=sql)


class ScopeViolation(RuntimeError):
    """A result set contained a store the requesting user may not see.

    This is a bug being caught, not a filter being applied. Reaching it means
    the generated SQL was missing its scope predicate, so the query itself was
    wrong — CLAUDE.md rule 5 requires the restriction to be in the WHERE
    clause, and this exists to prove it was.
    """


def check_scope(result: dict, visible_store_ids: set[int] | None) -> None:
    """Post-execution tripwire on the rows that came back.

    Rule 5 says restrict when building the query, never by dropping rows
    afterwards, and this does not drop anything — it refuses the whole result
    and raises. Filtering here would hide the defect; failing here surfaces it.

    Only fires when the result actually carries a store_id. A correctly scoped
    aggregate with no store_id column cannot be checked this way, which is a
    real limit of the tripwire and the reason it is a backstop rather than the
    mechanism.
    """
    if visible_store_ids is None:
        return
    try:
        index = result["columns"].index("store_id")
    except ValueError:
        return

    seen = {row[index] for row in result["rows"] if row[index] is not None}
    escaped = sorted(seen - visible_store_ids)
    if escaped:
        raise ScopeViolation(
            f"result contained store_id {escaped}, outside this user's scope "
            f"{sorted(visible_store_ids)}. The generated SQL was missing its "
            "scope predicate; the query is wrong, not just the output."
        )


def execute(
    conn: Any,
    sql: str,
    max_rows: int = DEFAULT_MAX_ROWS,
    visible_store_ids: set[int] | None = None,
) -> dict:
    """Run generated SQL under every guard and return columns plus rows.

    `conn` is a psycopg connection that should already be authenticated as the
    read-only role. Uses a named cursor so rows arrive in bounded batches
    rather than all at once.

    `visible_store_ids` enables the post-execution scope tripwire. Leave it
    None for an unscoped user (owner, or a manager with chain-wide access).
    """
    guarded = guard(sql, max_rows)

    with conn.cursor(name="guarded_read") as cur:
        cur.itersize = min(guarded.max_rows, 200)
        cur.execute(guarded.sql)
        rows = cur.fetchmany(guarded.max_rows)
        columns = [d.name for d in cur.description] if cur.description else []

    result = {
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "truncated": len(rows) >= guarded.max_rows,
        "executed_sql": guarded.sql,
    }
    check_scope(result, visible_store_ids)
    return result
