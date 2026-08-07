#!/usr/bin/env python3
"""Populate (or verify) the expected result sets in evals/sql/questions.jsonl.

The questions and their reference SQL are hand-written. The expected result
sets are NOT: they are produced by executing the reference SQL against the
seeded database, because a hand-typed result set is a second thing that can be
wrong, and a wrong expectation turns every eval score into noise.

This runs no model and needs no API key. It is not an eval — evals measure and
cost quota (ADR-0005); this just keeps a committed artifact in step with the
committed seed.

    python eval_expectations.py             # regenerate
    python eval_expectations.py --check     # fail if stale

Expectations are pinned to the seed by recording the SHA-256 of
seed/CHECKSUMS.txt. Regenerating the seed invalidates every expectation, and
--check says so rather than letting a stale number sit in the README.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = REPO_ROOT / "evals" / "sql" / "questions.jsonl"
SEED_CHECKSUMS = REPO_ROOT / "seed" / "CHECKSUMS.txt"

# all_matching questions are scored by set equality against the WHOLE true
# result, so the expectation has to hold every row. The ceiling is therefore
# SQL_MAX_ROWS: a question whose true result exceeds it cannot be scored,
# because the wrapper would truncate the model's answer. Such a question needs
# narrowing — see evals/README.md.
MAX_ROWS = 100


def seed_fingerprint() -> str:
    return hashlib.sha256(SEED_CHECKSUMS.read_bytes()).hexdigest()[:16]


def jsonable(value: object) -> object:
    """Stable JSON for values Postgres hands back.

    Decimal becomes a string, never a float: a float would round differently
    across platforms and make a committed expectation platform-dependent.
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    return str(value)


def load() -> list[dict]:
    return [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def dump(questions: list[dict]) -> str:
    return "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions)


def run(conn, sql: str, answer_columns: list[str] | None = None) -> dict:
    """Execute the reference and keep only the columns the question asks for.

    The reference SELECTs extra context because it is also read by humans. The
    EXPECTATION must not, because comparison requires every expected value to
    appear in the model's row — so an unasked-for column would demand the model
    guess it. Projecting here keeps the query readable and the expectation
    honest.
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        columns = [d.name for d in cur.description]
        rows = cur.fetchall()

    if answer_columns:
        missing = [c for c in answer_columns if c not in columns]
        if missing:
            raise KeyError(f"answer_columns not in reference output: {missing}")
        keep = [columns.index(c) for c in answer_columns]
        columns = answer_columns
        rows = [tuple(row[i] for i in keep) for row in rows]

    return {
        "columns": columns,
        "row_count": len(rows),
        "rows": [[jsonable(v) for v in row] for row in rows[:MAX_ROWS]],
        "truncated": len(rows) > MAX_ROWS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "READONLY_DATABASE_URL",
            os.environ.get("DATABASE_URL", ""),
        ),
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("Set READONLY_DATABASE_URL or DATABASE_URL, or run `make db` first.")
        return 2

    import psycopg

    questions = load()
    fingerprint = seed_fingerprint()
    updated: list[dict] = []
    failures: list[str] = []

    with psycopg.connect(args.database_url) as conn:
        conn.execute("SET default_transaction_read_only = on")
        for item in questions:
            fresh = dict(item)
            sql = item.get("reference_sql")
            if (
                item["expects"] in ("refusal", "disambiguation", "out_of_scope")
                or not sql
            ):
                # Refusals, scope rejections and disambiguations have no single
                # correct result set. They are scored on the shape of the
                # answer, and the scorer needs to know that rather than guess.
                fresh["expected"] = None
                fresh["seed_fingerprint"] = fingerprint
                updated.append(fresh)
                continue
            try:
                fresh["expected"] = run(conn, sql, item.get("answer_columns"))
            except Exception as exc:  # report, do not crash the whole run
                failures.append(f"{item['id']}: {type(exc).__name__}: {exc}")
                conn.rollback()
                fresh["expected"] = None
            fresh["seed_fingerprint"] = fingerprint
            updated.append(fresh)

    if failures:
        print(f"{len(failures)} reference queries failed:")
        for failure in failures:
            print(f"  {failure}")
        return 1

    # A question declared "rows" whose reference query returns nothing is a
    # broken question, not a finding: every wrong answer would score correct
    # against an empty expectation. Where empty genuinely IS the answer, the
    # question must say so with expects="empty".
    empty = [
        q["id"]
        for q in updated
        if q["expects"] == "rows" and q["expected"]["row_count"] == 0
    ]
    if empty:
        print(f"{len(empty)} reference queries returned NO ROWS: {', '.join(empty)}")
        print("An empty expectation scores every wrong answer as correct.")
        print('If empty is the correct answer, set expects="empty".')
        return 1

    oversized = [
        q["id"] for q in updated if q.get("expected") and q["expected"]["truncated"]
    ]
    if oversized:
        print(f"reference results exceed {MAX_ROWS} rows: {', '.join(oversized)}")
        print("The wrapper would truncate the model's answer, so these cannot")
        print("be scored. Narrow the question.")
        return 1

    wrongly_populated = [
        q["id"]
        for q in updated
        if q["expects"] == "empty" and q["expected"]["row_count"] != 0
    ]
    if wrongly_populated:
        print(f"declared empty but returned rows: {', '.join(wrongly_populated)}")
        return 1

    rendered = dump(updated)
    if args.check:
        if QUESTIONS.read_text(encoding="utf-8") == rendered:
            print(f"OK: {len(updated)} expectations current (seed {fingerprint})")
            return 0
        print("FAIL: evals/sql/questions.jsonl is stale.")
        print("Run `make eval-expectations` and commit the result.")
        return 1

    QUESTIONS.write_text(rendered, encoding="utf-8")
    rows_total = sum(q["expected"]["row_count"] for q in updated if q.get("expected"))
    print(
        f"wrote {len(updated)} expectations (seed {fingerprint}); "
        f"{rows_total} reference rows across "
        f"{sum(1 for q in updated if q.get('expected'))} queries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
