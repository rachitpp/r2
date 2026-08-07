"""Classifying one model answer against one expectation.

ADR-0001 threshold 1 turns on **silent-wrong**: a query that executes cleanly
and returns plausible wrong numbers. So the classification that matters most is
the distinction between "it broke" (recoverable, visible) and "it worked and
lied" (not). Those are different outcomes and are never merged here.

Deterministic execution-match only. No LLM-as-judge on structured queries — it
costs quota and comparing result sets costs nothing (ADR-0005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pos_copilot.tolerance import classify, values_match

INSUFFICIENT = "-- INSUFFICIENT SCHEMA"
OUT_OF_SCOPE = "-- OUT OF SCOPE"


class Outcome(StrEnum):
    CORRECT = "correct"
    WRONG_ROWS = "wrong_rows"
    WRONG_ORDER = "wrong_order"
    EXECUTION_ERROR = "execution_error"
    REFUSED_WRONGLY = "refused_wrongly"
    SHOULD_HAVE_REFUSED = "should_have_refused"
    WRONG_REFUSAL_KIND = "wrong_refusal_kind"
    NEEDS_REVIEW = "needs_review"

    @property
    def is_silent_wrong(self) -> bool:
        """Executed cleanly, returned the wrong answer, said nothing about it.

        SHOULD_HAVE_REFUSED counts: a confident answer to a question the data
        cannot support is the same failure wearing a different hat, and for
        q023 it is precisely the failure being tested.
        """
        return self in (
            Outcome.WRONG_ROWS,
            Outcome.WRONG_ORDER,
            Outcome.SHOULD_HAVE_REFUSED,
        )

    @property
    def is_correct(self) -> bool:
        return self is Outcome.CORRECT


@dataclass(frozen=True)
class Judgement:
    outcome: Outcome
    detail: str = ""


def strip_fences(text: str) -> str:
    """Models add markdown fences despite being asked not to."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:sql)?\s*\n(.*?)\n?```$", cleaned, re.S | re.I)
    if fence:
        return fence.group(1).strip()
    return cleaned


def refusal_kind(sql: str) -> str | None:
    head = strip_fences(sql).lstrip()
    if head.startswith(INSUFFICIENT):
        return "refusal"
    if head.startswith(OUT_OF_SCOPE):
        return "out_of_scope"
    return None


def normalise(value: object) -> str:
    """Compare values, not their formatting.

    A model writing 1234.5 where the reference wrote 1234.50 is right, and
    counting it wrong would inflate silent-wrong with formatting noise — which
    would then read as the tightest threshold firing.
    """
    if value is None:
        return "∅"
    if isinstance(value, bool):
        return str(value).lower()
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value).strip().casefold()
    if number == number.to_integral_value():
        return str(number.to_integral_value())
    return str(number.normalize())


def rows_of(result: dict) -> list[tuple[str, ...]]:
    return [tuple(normalise(v) for v in row) for row in result.get("rows", [])]


def row_contains(expected_row: list, columns: list[str], actual_row: list) -> bool:
    """Is every expected value present in the actual row, within tolerance?

    Sub-multiset, not equality. **Rows are the answer; columns are a projection
    over it.** Extra columns cannot make an answer wrong — a model returning
    supplier name alongside the payment terms has still answered — but a
    missing one can. The question fixes which rows come back, and almost never
    fixes which columns render them, so scoring on the projection measured
    whether the model guessed a SELECT list that existed only in the reference.

    Over-selection is not left entirely unmeasured: reaching for a column the
    read-only role cannot see fails at the permission layer instead.
    """
    remaining = list(actual_row)
    # Iterate the expected VALUES, not the column list. Zipping the two would
    # silently stop at the shorter one, so a missing or truncated `columns`
    # would leave the remaining values unchecked and pass everything.
    for index, want in enumerate(expected_row):
        column = columns[index] if index < len(columns) else ""
        kind = classify(column, want)
        for index, got in enumerate(remaining):
            if values_match(want, got, kind):
                del remaining[index]
                break
        else:
            return False
    return True


def _describe(row: list, columns: list[str]) -> str:
    pairs = [f"{c}={v!r}" for c, v in zip(columns, row, strict=False)]
    return ", ".join(pairs[:4]) + (" …" if len(pairs) > 4 else "")


#: What a question's text actually determines about its answer.
#:
#: The first eval run scored 0/4 because every reference carried an arbitrary
#: LIMIT the question never asked for — the model returned the right rows and
#: was marked wrong for not guessing the cutoff. A question that does not
#: determine its own answer cannot score one. See evals/README.md.
ORDERED_SHAPES = frozenset({"top_n", "ranked_all", "scalar"})
UNORDERED_SHAPES = frozenset({"all_matching"})


def compare(expected: dict, actual: dict, shape: str = "top_n") -> Judgement:
    """Compare result sets according to what the question determines.

    - `top_n` / `ranked_all` / `scalar` — the question fixes both the rows and
      their order, so comparison is an ordered exact match.
    - `all_matching` — the question fixes the rows but not their order, so
      comparison is **multiset equality against the whole true result**.

    Multiset equality, not containment. Over-fetching fails, because a loose
    predicate adds rows the reference does not have. Under-fetching fails too —
    a model capping at 20 rows where 30 match gives a different set, and an
    incomplete answer is a wrong answer. Ignoring the model's LIMIT means not
    penalising the *clause*; it never means not penalising its *effect*.
    """
    columns = expected.get("columns", [])
    want, got = expected.get("rows", []), actual.get("rows", [])

    if shape in UNORDERED_SHAPES:
        unmatched = list(got)
        missing = []
        for row in want:
            for index, candidate in enumerate(unmatched):
                if row_contains(row, columns, candidate):
                    del unmatched[index]
                    break
            else:
                missing.append(row)
        if not missing and not unmatched:
            return Judgement(Outcome.CORRECT)
        detail = f"set differs: {len(missing)} missing, {len(unmatched)} unexpected"
        if missing:
            detail += f"; first missing {_describe(missing[0], columns)}"
        return Judgement(Outcome.WRONG_ROWS, detail)

    if len(want) != len(got):
        return Judgement(
            Outcome.WRONG_ROWS, f"expected {len(want)} rows, got {len(got)}"
        )

    mismatched = [
        i
        for i, (a, b) in enumerate(zip(want, got, strict=False))
        if not row_contains(a, columns, b)
    ]
    if not mismatched:
        return Judgement(Outcome.CORRECT)

    # Same rows, wrong sequence: almost always a missing ORDER BY tiebreak.
    # Worth naming separately because the remedy is specific — and it is still
    # silent-wrong, because a ranked answer in the wrong order is wrong.
    pool = list(got)
    reordered = True
    for row in want:
        for index, candidate in enumerate(pool):
            if row_contains(row, columns, candidate):
                del pool[index]
                break
        else:
            reordered = False
            break
    if reordered and not pool:
        return Judgement(
            Outcome.WRONG_ORDER,
            "same rows in a different order — likely a missing ORDER BY tiebreak",
        )

    return Judgement(
        Outcome.WRONG_ROWS,
        f"{len(mismatched)} of {len(want)} rows differ; first at position "
        f"{mismatched[0]}, expected {_describe(want[mismatched[0]], columns)}",
    )


def judge(
    question: dict, generated_sql: str, execution: dict | None, error: str | None
) -> Judgement:
    """Classify one answer.

    `execution` is the result of running the generated SQL, or None if it was
    refused by the guard, failed, or the model declined to produce SQL.
    """
    expects = question["expects"]
    kind = refusal_kind(generated_sql)

    if expects in ("refusal", "out_of_scope"):
        if kind == expects:
            return Judgement(Outcome.CORRECT)
        if kind is not None:
            return Judgement(
                Outcome.WRONG_REFUSAL_KIND,
                f"declined with '{kind}' where '{expects}' was correct — a "
                "schema gap and a permission boundary are different failures",
            )
        return Judgement(
            Outcome.SHOULD_HAVE_REFUSED,
            "produced a query for a question that cannot honestly be answered",
        )

    if expects == "disambiguation":
        # No single right answer. Scored on whether the reply states which
        # reading it took, which needs a human.
        return Judgement(Outcome.NEEDS_REVIEW, "scored by hand against `intent`")

    if kind is not None:
        return Judgement(
            Outcome.REFUSED_WRONGLY,
            f"declined with '{kind}' but the data supports this",
        )

    if error is not None:
        return Judgement(Outcome.EXECUTION_ERROR, error)

    if execution is None:
        return Judgement(Outcome.EXECUTION_ERROR, "no result")

    if expects == "empty":
        if execution["row_count"] == 0:
            return Judgement(Outcome.CORRECT)
        return Judgement(
            Outcome.WRONG_ROWS,
            f"expected no rows, got {execution['row_count']}",
        )

    # A truncated result cannot be compared honestly — the missing rows are
    # unknowable from here. Surfacing it as its own failure keeps it from being
    # scored as a wrong answer when it is really a question that outgrew the cap.
    if execution.get("truncated"):
        return Judgement(
            Outcome.EXECUTION_ERROR,
            f"result truncated at {execution['row_count']} rows "
            f"({execution.get('total_row_count', 'unknown')} matched) — the "
            "question needs narrowing, or the cap raising",
        )

    return compare(
        question["expected"], execution, question.get("result_shape") or "top_n"
    )


def summarise(judgements: list[tuple[dict, Judgement]]) -> dict:
    """Aggregate into the numbers ADR-0001's thresholds are read from.

    Reported three ways — overall, view-covered, not-view-covered — because the
    Phase 0 views answer some questions almost directly, and the threshold is
    judged on the questions they do not.
    """
    from wilson import summarise as interval

    def bucket(items: list[tuple[dict, Judgement]]) -> dict:
        scorable = [(q, j) for q, j in items if j.outcome is not Outcome.NEEDS_REVIEW]
        correct = sum(1 for _, j in scorable if j.outcome.is_correct)
        n = len(scorable)
        return {
            "n": n,
            "correct": correct,
            "accuracy": interval(correct, n) if n else "n/a",
            "silent_wrong": [q["id"] for q, j in scorable if j.outcome.is_silent_wrong],
            "execution_errors": [
                q["id"] for q, j in scorable if j.outcome is Outcome.EXECUTION_ERROR
            ],
            "needs_review": [
                q["id"] for q, j in items if j.outcome is Outcome.NEEDS_REVIEW
            ],
        }

    return {
        "overall": bucket(judgements),
        "view_covered": bucket([p for p in judgements if p[0]["view_covered"]]),
        "not_view_covered": bucket([p for p in judgements if not p[0]["view_covered"]]),
    }
