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
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
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


_ORDER = re.compile(r"\bORDER\s+BY\b(.+?)(?:\bLIMIT\b|$)", re.S | re.I)
_LIMIT_TAIL = re.compile(r"\s*\bLIMIT\s+\d+\s*;?\s*$", re.I)


def tie_structure(conn, sql: str, answer_columns: list[str] | None) -> dict | None:
    """Where the ranking key repeats, and what could fill a contested slot.

    A reference's tiebreak — almost always `sku` — makes the query
    DETERMINISTIC, which is not the same as making the question DETERMINATE.
    Ties do two different things and both need recording:

    * **At the cut**, they decide WHICH ROWS ARE IN the answer at all. q042 has
      five of its ten slots contested among thirteen tied products.
    * **Inside the answer**, they make relative ORDER arbitrary. Rows tied on
      the ranking key can appear in any sequence and each is equally correct.

    `tie_keys` is the ranking value of each expected row, so the scorer can find
    the runs. `tie_pool` is the full set of rows sharing the boundary value,
    present only when the cut is contested. Returns None when the ranking key is
    unique throughout, which is the common case and scores exactly as before.
    """
    limit = re.search(r"\bLIMIT\s+(\d+)", sql, re.I)
    order = _ORDER.search(sql)
    if not (limit and order):
        return None
    n = int(limit.group(1))
    key = order.group(1).split(",")[0].strip()
    key = re.sub(r"\s+(ASC|DESC)(\s+NULLS\s+\w+)?\s*$", "", key, flags=re.I).strip()
    alias = key.split(".")[-1]

    with conn.cursor() as cur:
        cur.execute(_LIMIT_TAIL.sub("", sql))
        columns = [d.name for d in cur.description]
        rows = cur.fetchall()
    if alias not in columns:
        return None

    i = columns.index(alias)
    keys = [r[i] for r in rows]
    included = keys[:n]

    contested = len(rows) > n and keys[n - 1] == keys[n]
    interior = any(a == b for a, b in pairwise(included))
    if not (contested or interior):
        return None  # ranking key unique — nothing to relax

    pool = []
    if contested:
        boundary = keys[n - 1]
        pool = [r for r in rows if r[i] == boundary]
        if answer_columns:
            keep = [columns.index(c) for c in answer_columns]
            pool = [tuple(r[k] for k in keep) for r in pool]

    return {
        "tie_keys": [jsonable(k) for k in included],
        "tie_pool": [[jsonable(v) for v in r] for r in pool],
    }


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
                if item.get("result_shape") == "top_n":
                    tie = tie_structure(conn, sql, item.get("answer_columns"))
                    if tie:
                        fresh["expected"].update(tie)
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

    # newline="\n": this file carries every expected result set AND the seed
    # fingerprint each was computed against. Written with CRLF on Windows, git
    # normalises it to LF on commit (.gitattributes), so the committed bytes
    # differ from what was verified here — and CI's `git diff --exit-code` on
    # this path would fail for a reason that looks nothing like line endings.
    #
    # Fourth instance of the identical defect: corpus_ingest, corpus_generate
    # and seed.py were the others. Every one of them writes an artifact whose
    # bytes something downstream hashes or diffs.
    QUESTIONS.write_text(rendered, encoding="utf-8", newline="\n")
    rows_total = sum(q["expected"]["row_count"] for q in updated if q.get("expected"))
    print(
        f"wrote {len(updated)} expectations (seed {fingerprint}); "
        f"{rows_total} reference rows across "
        f"{sum(1 for q in updated if q.get('expected'))} queries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
