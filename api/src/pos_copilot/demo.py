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


def catalogue() -> list[str]:
    """What demo mode can answer — so the UI can offer them rather than guess."""
    return [p.question for p in load().values()]
