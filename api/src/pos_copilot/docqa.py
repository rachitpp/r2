"""Grounded document Q&A: retrieve, then answer from what was retrieved.

The sibling of `live.py`, and deliberately the same shape — question in;
answer, refusal or failure out, with the evidence either way. Where `live.py`
returns the SQL it generated so a reader can check it, this returns the chunks
it retrieved, for the same reason: an answer you cannot trace is an answer you
cannot check.

**Retrieval happens before a prompt exists.** Date and role filters are SQL
predicates in `retrieve()`, so a chunk outside the caller's scope or outside the
requested date is never fetched, never ranked, and never reaches the model
(rules 5 and 7). This module's job is to hand the survivors to the prompt as
data.

**The prompt is `retrieval_answer.md` unchanged.** It already carries the
delimited DOCUMENTS block and the security section, and it was measured against
four injection specimens in Phase 2. Nothing here interpolates a chunk into an
instruction position (rule 6); the one path that does is
`retrieval_answer_unsafe.md`, reached only by the injection demo.

**Three outcomes, kept apart**, because collapsing them is the failure demo
beat 2 exists to show:

    answered        documents were in force and the model answered from them
    none_in_force   documents exist for this scope, none covering that date
    not_found       no documents for this scope at all
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import env
from .model import Budget, BudgetExceeded, Provider, resolve_provider
from .retrieve import Chunk, format_documents, retrieve

PROMPT_NAME = "retrieval_answer.md"


@dataclass(frozen=True)
class DocAnswer:
    """One document answer, with what it was grounded in.

    `chunks` is present whenever retrieval ran, including when the outcome is
    `none_in_force` (where it is empty and that emptiness is the answer).
    """

    outcome: str
    answer: str | None = None
    error: str | None = None
    chunks: list[Chunk] = field(default_factory=list)
    as_of: date | None = None

    @property
    def citations(self) -> list[str]:
        seen: dict[str, None] = {}
        for chunk in self.chunks:
            seen.setdefault(chunk.citation(), None)
        return list(seen)


def as_of_date() -> date:
    """What this system means by "today" — never wall-clock.

    Same rule and same value as `live.py`: the seed has a fixed end date, so
    `current_date` is not today here and a date filter built from it silently
    returns nothing.
    """
    return date.fromisoformat(env.text("AS_OF_DATE", "2026-06-30"))


def load_prompt() -> str:
    from .prompts import PROMPTS_DIR

    return (PROMPTS_DIR / PROMPT_NAME).read_text(encoding="utf-8")


def render(question: str, documents: str, as_of: date) -> str:
    """Fill the template. Document text lands only in `{retrieved}`, which sits
    inside the DOCUMENTS block, below every instruction."""
    return (
        load_prompt()
        .replace("{question}", question)
        .replace("{retrieved}", documents)
        .replace("{as_of_date}", str(as_of))
    )


def ask(
    conn,
    question: str,
    *,
    embedder,
    as_of: date | None = None,
    supplier_id: int | None = None,
    store_id: int | None = None,
    doc_types: list[str] | None = None,
    limit: int = 6,
    provider: Provider | None = None,
    budget: Budget | None = None,
) -> DocAnswer:
    """Retrieve, then answer. One model call, or none."""
    on = as_of or as_of_date()

    found = retrieve(
        conn,
        question,
        as_of=on,
        embedder=embedder,
        supplier_id=supplier_id,
        store_id=store_id,
        doc_types=doc_types,
        limit=limit,
    )

    if not found.found:
        # No model call. There is nothing to ground an answer in, and asking the
        # model to say so anyway would spend quota to generate a sentence this
        # function already knows — and would give it the opportunity to answer
        # from general knowledge instead, which is the exact failure the
        # distinction exists to prevent.
        return DocAnswer(outcome=found.outcome, chunks=[], as_of=on)

    prompt = render(question, format_documents(found), on)
    provider = provider or resolve_provider("PLAN")
    budget = budget or Budget(max_calls=20, max_spend_usd=0.50)

    try:
        budget.check(prompt)
    except BudgetExceeded as exc:
        return DocAnswer(outcome="error", error=str(exc), chunks=found.chunks, as_of=on)

    try:
        text = provider.generate(prompt)
    except Exception as exc:  # pragma: no cover - provider-specific
        return DocAnswer(outcome="error", error=str(exc), chunks=found.chunks, as_of=on)
    budget.record(prompt)

    return DocAnswer(
        outcome="answered", answer=text.strip(), chunks=found.chunks, as_of=on
    )
