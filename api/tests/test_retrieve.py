"""Assertions for date- and role-filtered retrieval.

The SQL-building and scope logic is tested without a database, because that is
where the interesting failures live and because a test needing Postgres is a
test that does not run.

**The scope tests exist because the mechanism was, briefly, untestable.**
`doc_chunks.store_id` was NULL on every row until 2026-08-13, and the predicate
is `(store_id = %s OR store_id IS NULL)` — so a store-scoped query matched
everything and the restriction read as working. Any test written against that
data would have passed for the wrong reason. These assert on the SQL that is
built, so they hold whatever the data happens to contain.
"""

from __future__ import annotations

import pytest

from pos_copilot import retrieve as rt
from pos_copilot.readonly_sql import StoreRequired


class TestStoreScopeForRole:
    def test_an_unscoped_role_sees_the_whole_chain(self):
        assert rt.store_scope_for("manager", None) is None
        assert rt.store_scope_for("owner", None) is None

    def test_an_unscoped_role_is_not_narrowed_by_a_passed_store(self):
        """A manager who happens to send a store still sees chain-wide. The
        role decides the ceiling; the parameter cannot raise it or lower it."""
        assert rt.store_scope_for("manager", 2) is None

    def test_a_scoped_role_is_held_to_its_store(self):
        assert rt.store_scope_for("clerk", 2) == 2

    def test_a_scoped_role_with_no_store_refuses(self):
        """Never answered by picking one. A defaulted store is the wrong shop's
        invoices wearing the right shop's label — the same refusal
        `readonly_sql.visible_stores` makes, deliberately worded the same way."""
        with pytest.raises(StoreRequired):
            rt.store_scope_for("clerk", None)


class TestScopeSql:
    def test_no_scope_is_a_true_predicate_not_an_absent_one(self):
        """`TRUE` rather than an empty string, so the caller can always
        interpolate it into a WHERE clause without building SQL by cases."""
        sql, params = rt._scope_sql(None, None)
        assert sql == "TRUE"
        assert params == []

    def test_a_store_scope_also_matches_null(self):
        """THE LOAD-BEARING ONE. A policy carries store_id NULL because it
        applies chain-wide. Matching only the store drops every policy from a
        clerk's results, which reads as a thin corpus rather than a wrong
        filter — silent, and wrong in the direction nobody checks."""
        sql, params = rt._scope_sql(None, 2)
        assert "c.store_id = %s" in sql
        assert "c.store_id IS NULL" in sql
        assert params == [2]

    def test_a_supplier_scope_also_matches_null(self):
        sql, params = rt._scope_sql(7, None)
        assert "c.supplier_id = %s" in sql
        assert "c.supplier_id IS NULL" in sql
        assert params == [7]

    def test_both_scopes_are_anded(self):
        sql, params = rt._scope_sql(7, 2)
        assert " AND " in sql
        assert params == [7, 2]


class TestRetrievalOutcome:
    def test_found_is_the_only_outcome_that_reports_found(self):
        empty_gap = rt.Retrieval(chunks=[], outcome="none_in_force", as_of=None)
        empty_missing = rt.Retrieval(chunks=[], outcome="not_found", as_of=None)
        assert not empty_gap.found
        assert not empty_missing.found

    def test_none_in_force_and_not_found_are_kept_apart(self):
        """Collapsing them into "no results" is the failure demo beat 2 exists
        to show: "there was no contract that month" and "we have nothing for
        this supplier" are different answers to different questions."""
        assert "none_in_force" != "not_found"


class TestFormatting:
    def test_a_citation_carries_the_document_and_its_effective_date(self):
        from datetime import date

        chunk = rt.Chunk(
            doc_id="contract-sup-01-20250629",
            doc_type="contract",
            chunk_index=0,
            content="Net 30 days.",
            effective_from=date(2025, 6, 29),
            effective_to=None,
            similarity=0.9,
        )
        assert chunk.citation() == "[contract-sup-01-20250629, effective 2025-06-29]"

    def test_an_empty_retrieval_says_so_rather_than_rendering_nothing(self):
        """An empty DOCUMENTS block reads to the model as "no documents were
        given", which invites an answer from general knowledge. Saying that
        nothing was in force is a different instruction."""
        rendered = rt.format_documents(
            rt.Retrieval(chunks=[], outcome="none_in_force", as_of=None)
        )
        assert "no documents" in rendered.lower()

    def test_each_chunk_is_rendered_with_its_own_validity(self):
        from datetime import date

        chunks = [
            rt.Chunk(
                "doc-a", "contract", 0, "A", date(2024, 1, 1), date(2025, 1, 1), 0.9
            ),
            rt.Chunk("doc-b", "policy", 0, "B", date(2025, 1, 1), None, 0.8),
        ]
        rendered = rt.format_documents(
            rt.Retrieval(chunks=chunks, outcome="found", as_of=date(2025, 6, 1))
        )
        assert "doc-a" in rendered and "2024-01-01" in rendered
        assert "doc-b" in rendered and "further notice" in rendered
