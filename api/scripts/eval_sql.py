#!/usr/bin/env python3
"""Run the SQL eval set and report execution accuracy.

Evals measure; they do not assert (ADR-0005). This never runs in CI and never
gates anything — it produces the numbers that go in the README.

    # plumbing check, no key needed
    python eval_sql.py --provider stub --limit 5

    # staged: prove the runner, then one pass, then three
    python eval_sql.py --limit 5 --runs 1
    python eval_sql.py --runs 1
    python eval_sql.py --runs 3

Serial by design. RPM is the first ceiling on a free tier, so there is no
concurrency and the pacer keeps request starts a fixed interval apart, with
full-jitter exponential backoff on 429.

Responses are cached on (prompt fingerprint, question id, run index). Editing
any prompt or context file changes the fingerprint and invalidates the cache,
because the model would now be sent something different.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pos_copilot import env
from pos_copilot.model import (
    Budget,
    BudgetExceeded,
    Pacer,
    ResponseCache,
    StubProvider,
    resolve_provider,
)
from pos_copilot.prompts import bundle_fingerprint, load_sql_prompt
from pos_copilot.readonly_sql import UnsafeQuery, execute
from pos_copilot.scoring import (
    Outcome,
    judge,
    strip_fences,
    summarise,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = REPO_ROOT / "evals" / "sql" / "questions.jsonl"
RESULTS_DIR = REPO_ROOT / "evals" / "results"


def load_questions() -> list[dict]:
    return [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def scope_ids(question: dict) -> set[int] | None:
    """Which stores this question's user may see, for the tripwire."""
    scope = question.get("store_scope", "all stores")
    if scope == "all stores":
        return None
    digits = "".join(ch for ch in scope.split("(")[0] if ch.isdigit())
    return {int(digits)} if digits else None


def build_stub(questions: list[dict]) -> StubProvider:
    """A stub that answers from the reference SQL, with seeded failures.

    Not an oracle: three questions are answered wrongly on purpose so a run
    against the stub exercises every branch of the scorer. A runner only ever
    tested on correct answers proves nothing about how it reports bad ones.
    """
    responses: dict[str, str] = {}
    for q in questions:
        if q["expects"] == "refusal":
            responses[q["question"]] = "-- INSUFFICIENT SCHEMA: not in the schema"
        elif q["expects"] == "out_of_scope":
            responses[q["question"]] = "-- OUT OF SCOPE: this user can only see Pune"
        elif q["reference_sql"]:
            responses[q["question"]] = q["reference_sql"]

    # Seeded failures, one of each interesting kind.
    if "q001" in {q["id"] for q in questions}:
        by_id = {q["id"]: q for q in questions}
        if "q002" in by_id:  # silent-wrong: right shape, wrong rows
            responses[by_id["q002"]["question"]] = (
                "SELECT sku, product_name, category_name, units_per_day "
                "FROM v_stock_status WHERE store_id = 2 AND on_hand = 0 "
                "ORDER BY units_per_day DESC, sku LIMIT 15"
            )
        if "q039" in by_id:  # refused a question the data supports
            responses[by_id["q039"]["question"]] = (
                "-- INSUFFICIENT SCHEMA: pretending this is unanswerable"
            )
        if "q033" in by_id:  # execution error
            responses[by_id["q033"]["question"]] = "SELECT * FROM no_such_table"
    return StubProvider(responses=responses)


def run(args: argparse.Namespace) -> int:
    import psycopg

    questions = load_questions()
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    bundle = load_sql_prompt()
    fingerprint = bundle_fingerprint(bundle.hashes)

    if args.provider == "stub":
        provider = build_stub(load_questions())
        cache = ResponseCache(enabled=False)
    else:
        provider = resolve_provider("PLAN")
        cache = ResponseCache(enabled=not args.no_cache)

    total_calls = len(questions) * args.runs
    print(f"provider   {provider.name} / {provider.model}")
    print(f"prompt     {fingerprint}")
    print(f"questions  {len(questions)} x {args.runs} runs = {total_calls} calls")
    if args.provider != "stub":
        pacer = getattr(provider, "pacer", Pacer())
        print(f"pacing     {pacer.rpm} rpm -> {pacer.min_interval:.1f}s between starts")
        print(f"estimate   {total_calls * pacer.min_interval / 60:.1f} min minimum")
    print()

    budget = Budget(max_calls=args.max_calls, max_spend_usd=args.max_spend)
    url = args.database_url
    judgements: list[tuple[dict, object]] = []
    per_question_outcomes: dict[str, list[str]] = {}

    # One short-lived connection per query, opened only around the execution.
    #
    # A single long-lived connection does not work here and should not: the
    # read-only role sets idle_in_transaction_session_timeout = 10s, and the
    # model call between two queries takes longer than that once pacing is
    # added. Postgres terminates the connection, correctly. Holding a database
    # transaction open across a network call to a third party is the actual
    # mistake; the timeout just makes it visible.
    for run_index in range(args.runs):
        for q in questions:
            prompt = bundle.render(
                question=q["question"],
                as_of_date=env.text("AS_OF_DATE", "2026-06-30"),
                user_role=q.get("user_role", "owner"),
                store_scope=q.get("store_scope", "all stores"),
            )

            cached = cache.get(fingerprint, q["id"], run_index)
            if cached is None:
                budget.check(prompt)
                cached = provider.generate(prompt)
                budget.record(prompt)
                cache.put(fingerprint, q["id"], run_index, cached)

            sql = strip_fences(cached)
            execution, error = None, None
            if not sql.lstrip().startswith("--"):
                try:
                    with psycopg.connect(url) as conn:
                        execution = execute(
                            conn,
                            sql,
                            max_rows=env.integer("SQL_MAX_ROWS", 100),
                            visible_store_ids=scope_ids(q),
                        )
                except UnsafeQuery as exc:
                    error = f"refused by guard: {exc}"
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"

            verdict = judge(q, sql, execution, error)
            judgements.append((q, verdict))
            per_question_outcomes.setdefault(q["id"], []).append(str(verdict.outcome))

            mark = {
                Outcome.CORRECT: "ok  ",
                Outcome.NEEDS_REVIEW: "?   ",
            }.get(verdict.outcome, "FAIL")
            print(
                f"  {mark} {q['id']} run{run_index}  {verdict.outcome}"
                f"{'  — ' + verdict.detail if verdict.detail else ''}"
            )

    print(f"\nspent {budget.calls} calls, ~${budget.spend_usd:.2f} estimated")
    stats = summarise(judgements)

    # Cross-run variance: how often a question does not give the same outcome
    # every time. With sampling parameters deprecated this measures the model's
    # inherent nondeterminism, not prompt instability — see ADR-0006.
    unstable = [
        qid for qid, outs in per_question_outcomes.items() if len(set(outs)) > 1
    ]
    variance = len(unstable) / max(1, len(per_question_outcomes))

    print("\n" + "=" * 66)
    for scope in ("overall", "view_covered", "not_view_covered"):
        block = stats[scope]
        print(f"{scope:<18} {block['accuracy']}")
    print(
        f"{'silent-wrong':<18} {len(stats['overall']['silent_wrong'])} "
        f"{stats['overall']['silent_wrong'] or ''}"
    )
    print(
        f"{'execution errors':<18} {len(stats['overall']['execution_errors'])} "
        f"{stats['overall']['execution_errors'] or ''}"
    )
    print(
        f"{'needs review':<18} {len(stats['overall']['needs_review'])} "
        f"{stats['overall']['needs_review'] or ''}"
    )
    if args.runs > 1:
        print(f"{'cross-run variance':<18} {variance:.1%} {unstable or ''}")
    if cache.enabled:
        print(f"{'cache':<18} {cache.hits} hits, {cache.misses} misses")
    print("=" * 66)
    print(
        "\nADR-0001 threshold 2 is read off not_view_covered, and only when "
        "the interval excludes 85%."
    )

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{stamp}-sql.json"
    out.write_text(
        json.dumps(
            {
                "provider": provider.name,
                "model": provider.model,
                "prompt_fingerprint": fingerprint,
                "prompt_hashes": bundle.hashes,
                "runs": args.runs,
                "questions": len(questions),
                "stats": stats,
                "cross_run_variance": variance,
                "unstable_questions": unstable,
                "outcomes": per_question_outcomes,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("gemini", "stub"), default="gemini")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="", help="comma-separated question ids")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--max-calls",
        type=int,
        default=250,
        help="hard ceiling; the run stops itself rather than looping away",
    )
    parser.add_argument("--max-spend", type=float, default=25.0)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "READONLY_DATABASE_URL",
            "postgresql://pos_readonly:pos_readonly_dev@localhost:5432/pos",
        ),
    )
    try:
        return run(parser.parse_args(argv))
    except BudgetExceeded as exc:
        print(f"\nBUDGET STOP: {exc}")
        print("Cached answers are kept, so a resumed run costs only the rest.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
