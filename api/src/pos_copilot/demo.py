"""Demo mode: answering without a key, a network call, or a penny of quota.

CLAUDE.md rule 2 — **the system a reader runs must never need paid inference.**
So the live path uses the reader's own credentials and this path uses none at
all. A clone of the repo with a database and no API key answers demo beat 1.

The pairs live in `api/demo/queries.json` and are **deliberately not** the eval
reference queries. `evals/sql/questions.jsonl` is the measuring instrument, it
is under repair, and serving answers from it would put known-wrong numbers in
front of a reader. Two artifacts, two purposes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: api/src/pos_copilot/demo.py -> parents[2] is api/
API_ROOT = Path(__file__).resolve().parents[2]
DEMO_FILE = API_ROOT / "demo" / "queries.json"

#: Substituted into store-scoped SQL. Rule 5 says the scope predicate belongs in
#: the query; this is how it gets there in demo mode.
STORE_TOKEN = "{store_id}"


class DemoUnavailable(LookupError):
    """No canned answer for this question. Not an error — a boundary."""


@dataclass(frozen=True)
class DemoPair:
    question: str
    sql: str | None
    refusal: str | None
    store_scoped: bool

    def resolve(self, store_id: int | None) -> str:
        """The SQL to run, with the scope predicate filled in."""
        if self.sql is None:
            raise DemoUnavailable("this question is answered by a refusal")
        if not self.store_scoped:
            return self.sql
        if store_id is None:
            raise DemoUnavailable(
                "this question is about a specific store and none was given"
            )
        # store_id is an int by the time it reaches here — the request model
        # validates it — and the result still passes through readonly_sql.guard.
        return self.sql.replace(STORE_TOKEN, str(int(store_id)))


def normalise(question: str) -> str:
    """Match on words, not on punctuation or spacing.

    Deliberately crude: demo mode is a fixed menu, not a matcher. Anything it
    does not recognise is a `DemoUnavailable`, which the caller reports plainly
    rather than guessing at.
    """
    return re.sub(r"[^a-z0-9 ]+", "", question.lower()).strip()


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict[str, DemoPair]:
    raw = json.loads(Path(path or DEMO_FILE).read_text())
    pairs = {}
    for entry in raw["pairs"]:
        pair = DemoPair(
            question=entry["question"],
            sql=entry.get("sql"),
            refusal=entry.get("refusal"),
            store_scoped=bool(entry.get("store_scoped", False)),
        )
        if pair.sql is None and pair.refusal is None:
            raise ValueError(f"demo pair {pair.question!r} has neither SQL nor refusal")
        if pair.store_scoped and pair.sql and STORE_TOKEN not in pair.sql:
            raise ValueError(
                f"demo pair {pair.question!r} is store_scoped but its SQL has no "
                f"{STORE_TOKEN} — the scope predicate would be missing entirely"
            )
        pairs[normalise(pair.question)] = pair
    return pairs


def lookup(question: str) -> DemoPair:
    try:
        return load()[normalise(question)]
    except KeyError:
        raise DemoUnavailable(
            "demo mode answers a fixed set of questions and this is not one of "
            "them. Set DEMO_MODE=false and supply credentials for the live path."
        ) from None


def catalogue() -> list[dict]:
    """What demo mode can answer, **and what each question needs or does**.

    Returning bare strings was a defect, not a simplification. Two things the
    caller cannot recover from a list of questions:

    1. **Which questions need a store.** A UI that cannot tell has to infer, and
       the first move of an inferring UI is to guess and default — which is
       precisely what `DemoPair.resolve` refuses to do, reintroduced one layer
       up. `requires_store` is that refusal made visible to the caller.
    2. **Which question refuses.** The refusal is the strongest thing in the
       demo — ADR-0002's pattern-not-people constraint visible in the product
       rather than asserted in a document — and it is worth *offering*
       deliberately rather than leaving a reader to stumble on it. `expect`
       lets a UI label it as a demonstration instead of showing it as one of
       five equivalent questions.
    """
    return [
        {
            "question": p.question,
            "requires_store": p.store_scoped,
            "expect": "refusal" if p.sql is None else "answer",
        }
        for p in load().values()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Demo beat 2 — document answers
#
# Same principle as the SQL pairs above and a different shape, because the two
# beats cost different things. Beat 1 replays SQL and executes it for real. Here
# RETRIEVAL IS ALREADY FREE — embeddings are local (rule 2) — so retrieval runs
# for real and only the answer text is replayed. A reader sees the citations
# retrieval actually produced.
#
# Every answer in documents.json was produced by the real model and copied from
# corpus/injection/traces/retrieval-injection.json. A hand-written demo answer
# would be a claim nobody measured, and this is the easiest place in the repo to
# hide one.
# ─────────────────────────────────────────────────────────────────────────────

DOCUMENTS_FILE = API_ROOT / "demo" / "documents.json"


@dataclass(frozen=True)
class DemoDocAnswer:
    """One replayed document answer, keyed by question AND date.

    `answer` is None for the none_in_force case, and that is not a missing
    value: the live path makes no model call there, so there is no output to
    replay. Storing a sentence would invent one.
    """

    question: str
    as_of: str
    supplier_code: str | None
    doc_types: list[str] | None
    answer: str | None
    outcome: str


@lru_cache(maxsize=1)
def _document_answers() -> list[DemoDocAnswer]:
    if not DOCUMENTS_FILE.is_file():
        return []
    raw = json.loads(DOCUMENTS_FILE.read_text(encoding="utf-8"))
    return [
        DemoDocAnswer(
            question=entry["question"],
            as_of=entry["as_of"],
            supplier_code=entry.get("supplier_code"),
            doc_types=entry.get("doc_types"),
            answer=entry.get("answer"),
            outcome=entry.get("outcome", "answered"),
        )
        for entry in raw.get("answers", [])
    ]


def document_catalogue() -> list[dict]:
    """What demo mode can answer about documents, and at which dates.

    The date is part of the key, so it has to be part of the catalogue — a UI
    that offered the question without its dates would let a reader pick a
    combination that has no answer and read the 404 as the system failing.
    """
    return [
        {
            "question": entry.question,
            "as_of": entry.as_of,
            "supplier_code": entry.supplier_code,
            "outcome": entry.outcome,
        }
        for entry in _document_answers()
    ]


def lookup_document(question: str, as_of: str) -> DemoDocAnswer:
    """Find the replayed answer for this question at this date.

    Matched on normalised question text and exact date. **No nearest-date
    fallback**: serving the answer from a neighbouring date would be the demo
    silently contradicting the one property beat 2 exists to show.
    """
    wanted = normalise(question)
    for entry in _document_answers():
        if normalise(entry.question) == wanted and entry.as_of == as_of:
            return entry
    raise DemoUnavailable(
        f"demo mode has no document answer for {question!r} as of {as_of}. "
        "Answers are keyed by date on purpose; there is no nearest-date "
        "fallback, because serving one would contradict the thing this beat "
        "demonstrates. Set DEMO_MODE=false to ask it live."
    )
