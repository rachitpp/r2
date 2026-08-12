"""Assertions for the extraction scorer.

Every one of these pins a defect the scorer actually had on its first run
against real output. It reported **42.2% header accuracy against an extraction
that was very nearly perfect**, then **rewarded a hallucination and penalised a
refusal**, before any of it was true of the model. A scorer is an instrument,
and an instrument that has never been wrong has never been checked.

No database and no model: these exercise the comparison and the shaping, which
is where the bugs were.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import eval_extraction as ev


class TestEqual:
    def test_money_matches_within_a_cent(self):
        assert ev.equal(2119.5, "2119.50")
        assert ev.equal("8000", 8000)

    def test_money_beyond_tolerance_does_not_match(self):
        assert not ev.equal(2119.5, 2119.6)

    def test_html_entities_do_not_quietly_compare_equal(self):
        """`&amp;` reaching the PDF is a corpus defect worth surfacing. A
        lenient text comparison is exactly how that finding would have been
        lost — it would have scored as a pass and never been written down."""
        assert not ev.equal("Godavari Grains &amp; Pulses", "Godavari Grains & Pulses")

    def test_null_matches_only_null(self):
        assert ev.equal(None, None)
        assert not ev.equal(None, "SUP-01")
        assert not ev.equal("SUP-01", None)


class TestFlatten:
    def test_contract_clauses_are_lifted_where_scoring_can_see_them(self):
        """The bug that produced 42.2%.

        A contract carries `clauses`, not top-level term fields — that is the
        clause-level provenance decision working. The first scorer read the top
        level, found None every time, and published a confident number about a
        field it was not looking at.
        """
        data = {
            "supplier_code": "SUP-01",
            "clauses": [
                {"clause": "payment_terms_days", "value": 14},
                {"clause": "returns_window_days", "value": 28},
            ],
        }
        flat = ev.flatten("contract", data)
        assert flat["payment_terms_days"] == 14
        assert flat["returns_window_days"] == 28
        assert flat["supplier_code"] == "SUP-01"

    def test_flatten_leaves_other_types_alone(self):
        data = {"subtotal": 10.0}
        assert ev.flatten("invoice", data) == data


class TestHeaderFields:
    def test_catalogs_do_not_score_supplier_code(self):
        """No catalog prints one. Scoring it meant two extractions scored
        CORRECT for inferring `SUP-01` from the supplier name while the one that
        honestly returned null scored as a MISS — the metric rewarding the
        hallucination and penalising the refusal."""
        assert "supplier_code" not in ev.HEADER_FIELDS["catalog"]

    def test_invoices_do_score_supplier_code(self):
        """Invoices genuinely print `Supplier code | SUP-01`, so it is real
        extraction there rather than inference. The exclusion above is about
        what the document contains, not about the field being hard."""
        assert "supplier_code" in ev.HEADER_FIELDS["invoice"]


class TestAmendments:
    def test_amendments_are_excluded_and_counted(self):
        """A wide superseding row carries clauses the amendment deliberately
        does not restate, so scoring them measures the inheritance. Excluded —
        but counted, so the denominator cannot shrink silently."""
        tally = ev.Tally()
        ev.score_document(
            "contract",
            {"clauses": []},
            {"header": {"payment_terms_days": 30}, "rows": []},
            tally,
            "contract-sup-04-20251018",
        )
        assert tally.total == 0
        assert tally.unscorable == 1

    def test_a_normal_contract_is_still_scored(self):
        tally = ev.Tally()
        ev.score_document(
            "contract",
            {"clauses": [{"clause": "payment_terms_days", "value": 30}]},
            {"header": {"payment_terms_days": 30}, "rows": []},
            tally,
            "contract-sup-01-20250629",
        )
        assert tally.total == 1
        assert tally.correct == 1


class TestCatalogDates:
    def test_a_catalog_date_is_compared_by_month(self):
        """The document prints `November 2025`. The manifest key carries the day
        the prices were selected on, which was never printed anywhere, so
        demanding it scored the model wrong for reading its own document right.
        """
        tally = ev.Tally()
        ev.score_document(
            "catalog",
            {"effective_from": "2025-11-01"},
            {"header": {"effective_from": "2025-11-03"}, "rows": []},
            tally,
            "catalog-sup-01-20251103",
        )
        assert tally.correct == 1

    def test_a_catalog_in_the_wrong_month_still_fails(self):
        """Month granularity is not no granularity."""
        tally = ev.Tally()
        ev.score_document(
            "catalog",
            {"effective_from": "2025-12-01"},
            {"header": {"effective_from": "2025-11-03"}, "rows": []},
            tally,
            "catalog-sup-01-20251103",
        )
        assert tally.correct == 0


class TestRows:
    def test_a_missing_row_counts_as_a_miss_not_a_pass(self):
        tally = ev.Tally()
        ev.score_rows(
            "catalog",
            {"prices": []},
            {"rows": [{"key": "FNV-0001", "unit_price": 18.19}]},
            tally,
        )
        assert tally.missed == 1
        assert tally.total == 1
        assert tally.correct == 0

    def test_an_invented_row_counts_as_hallucination(self):
        tally = ev.Tally()
        ev.score_rows(
            "catalog",
            {"prices": [{"product_code": "NOPE-9999", "unit_price": 1.0}]},
            {"rows": []},
            tally,
        )
        assert tally.hallucinated == 1
        assert tally.correct == 0

    def test_a_right_row_with_a_wrong_price_is_not_correct(self):
        tally = ev.Tally()
        ev.score_rows(
            "catalog",
            {"prices": [{"product_code": "FNV-0001", "unit_price": 99.99}]},
            {"rows": [{"key": "FNV-0001", "unit_price": 18.19}]},
            tally,
        )
        assert tally.correct == 0
        assert tally.hallucinated == 1


class TestTally:
    def test_an_empty_tally_has_no_rate_rather_than_zero(self):
        """0/0 is not 0%. Printing a rate with no denominator is how the Phase 1
        eval published a number that described nothing."""
        assert ev.Tally().rate() is None
