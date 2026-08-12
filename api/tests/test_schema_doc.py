"""Assertions for what reaches the text-to-SQL context.

`schema.md` is the context the SQL-generating model reads, and it is generated
from `COMMENT ON` statements so it cannot drift from the schema (ADR-0008). What
it must ALSO not do is carry tables a business question can never be about.

Until 2026-08-13 `schema_doc.sql` had no filter, so `doc_chunks` — with a
`vector(384)` column — went into the SQL prompt the moment Phase 3 landed, and
the agent tables followed in Phase 4. These tests read the committed file, so
they need no database and they fail on the artifact a reader actually gets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCHEMA_MD = Path(__file__).resolve().parents[1] / "prompts" / "context" / "schema.md"

#: Infrastructure. Retrieval indexes and agent state are how this project is
#: built, not things a shop is asked about.
EXCLUDED = ["doc_chunks", "agent_runs", "proposed_actions", "agent_events"]

#: Business data that must stay. supplier_term_clauses is what a document SAYS,
#: clause by clause — a legitimate subject for a question, unlike the others.
INCLUDED = [
    "supplier_terms",
    "supplier_term_clauses",
    "products",
    "sale_lines",
    "purchase_orders",
]


@pytest.fixture(scope="module")
def schema_md() -> str:
    return SCHEMA_MD.read_text(encoding="utf-8")


@pytest.mark.parametrize("table", EXCLUDED)
def test_infrastructure_stays_out_of_the_sql_context(schema_md: str, table: str):
    """Noise in the prompt, another fingerprint move, and — because
    pos_readonly can SELECT these — a model that sees them can write queries
    against them."""
    assert f"## `{table}`" not in schema_md, (
        f"{table} is infrastructure and reached the text-to-SQL context. "
        "Add it to the NOT IN list in api/scripts/schema_doc.sql."
    )


@pytest.mark.parametrize("table", INCLUDED)
def test_business_tables_are_present(schema_md: str, table: str):
    """The filter defaults to INCLUDE for exactly this reason: a filter that
    quietly drops business data is worse than one that lets noise through,
    because the model then answers from a schema missing the answer."""
    assert f"## `{table}`" in schema_md, f"{table} is missing from the SQL context"


def test_no_vector_column_reaches_the_prompt(schema_md: str):
    """`embedding vector(384)` is not queryable in any sense a user means, and
    its presence was the clearest sign the file had no filter at all."""
    assert "vector(384)" not in schema_md
