"""Extraction schemas, validation, and the runner's plumbing.

Everything here runs against the stub: no key, no network, no quota (ADR-0005 —
tests assert, evals measure). Nothing in this file claims anything about whether
the model extracts *correctly*; that is the gold set's job and it does not exist
yet.
"""

from __future__ import annotations

import json

import corpus_extract
import pytest

from pos_copilot import extract
from pos_copilot.prompts import bundle_fingerprint, load_extract_prompt


def contract(**overrides) -> dict:
    base = {
        "readable": True,
        "supplier_code": "SUP-04",
        "supplier_name": "Deccan Oils & Provisions",
        "document_kind": "amendment",
        "effective_from": "2025-10-18",
        "effective_to": None,
        "clauses": [
            {
                "clause": "payment_terms_days",
                "clause_number": "3",
                "value": 60,
                "verbatim": "Net 60 days from invoice date.",
            }
        ],
    }
    return base | overrides


class TestFences:
    def test_strips_a_json_tagged_fence(self):
        assert extract.strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_an_untagged_fence(self):
        assert extract.strip_json_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_leaves_bare_json_alone(self):
        assert extract.strip_json_fences('{"a": 1}') == '{"a": 1}'


class TestValidateContract:
    def test_a_well_formed_amendment_passes(self):
        assert extract.validate("contract", contract()) == []

    def test_an_amendment_with_three_clauses_passes(self):
        """The whole point of the narrow shape.

        contract-sup-04-20251018 varies clauses 3, 4 and 7 and restates nothing
        else. A correct extraction holds three clauses, and nothing may require
        the two it does not mention.
        """
        data = contract(
            clauses=[
                {"clause": c, "clause_number": n, "value": v, "verbatim": "..."}
                for c, n, v in [
                    ("payment_terms_days", "3", 60),
                    ("lead_time_days", "4", 7),
                    ("returns_window_days", "7", 28),
                ]
            ]
        )
        assert extract.validate("contract", data) == []

    def test_an_unknown_clause_name_is_an_error(self):
        data = contract(
            clauses=[{"clause": "delivery_window", "value": 3, "verbatim": "x"}]
        )
        errors = extract.validate("contract", data)
        assert any("not a known term" in e for e in errors)

    def test_a_clause_stated_twice_is_an_error(self):
        row = {"clause": "lead_time_days", "value": 7, "verbatim": "x"}
        errors = extract.validate("contract", contract(clauses=[row, dict(row)]))
        assert any("more than once" in e for e in errors)

    def test_a_string_value_is_an_error(self):
        """ "Net 60" is a plausible-looking answer and an unusable one."""
        data = contract(
            clauses=[{"clause": "payment_terms_days", "value": "60", "verbatim": "x"}]
        )
        errors = extract.validate("contract", data)
        assert any("not a number" in e for e in errors)

    def test_no_clauses_at_all_is_an_error(self):
        assert extract.validate("contract", contract(clauses=[])) != []

    def test_a_non_iso_date_is_an_error(self):
        errors = extract.validate("contract", contract(effective_from="18 Oct 2025"))
        assert any("not an ISO date" in e for e in errors)

    def test_a_null_effective_to_is_fine(self):
        """ "Until further notice" is a real state, not a missing value."""
        assert extract.validate("contract", contract(effective_to=None)) == []

    def test_unreadable_short_circuits(self):
        """An honest refusal must not then be failed for being empty."""
        assert extract.validate("contract", {"readable": False}) == []


class TestValidateOtherTypes:
    def test_invoice_requires_its_numbers(self):
        errors = extract.validate(
            "invoice",
            {
                "readable": True,
                "invoice_number": "5316",
                "invoice_date": "2025-04-02",
                "subtotal": "one hundred",
                "tax_total": 5.0,
                "total": 105.0,
                "line_items": [],
            },
        )
        assert any("subtotal is not a number" in e for e in errors)

    def test_catalog_needs_an_effective_date(self):
        errors = extract.validate(
            "catalog", {"readable": True, "effective_from": None, "prices": []}
        )
        assert any("effective_from is required" in e for e in errors)

    def test_policy_may_be_undated(self):
        data = {
            "readable": True,
            "policy_name": "Cold chain",
            "effective_from": None,
            "rules": [{"heading": "Storage", "statement": "Below 4C."}],
        }
        assert extract.validate("policy", data) == []


class TestReconciliation:
    def test_line_items_that_sum_to_the_subtotal(self):
        data = {
            "subtotal": 300.0,
            "line_items": [{"line_total": 100.0}, {"line_total": 200.0}],
        }
        assert extract.reconciles(data) is True

    def test_a_dropped_line_item_is_detectable(self):
        """The corpus's one free correctness signal, with no gold label."""
        data = {"subtotal": 300.0, "line_items": [{"line_total": 100.0}]}
        assert extract.reconciles(data) is False

    def test_unknown_when_the_check_cannot_run(self):
        assert extract.reconciles({"subtotal": 300.0, "line_items": []}) is None


class TestParse:
    def test_a_bad_response_is_a_result_not_an_exception(self):
        result = extract.parse("d1", "contract", "I could not read that document.")
        assert result.data is None
        assert not result.ok
        assert result.raw == "I could not read that document."

    def test_a_json_array_is_rejected(self):
        result = extract.parse("d1", "contract", "[1, 2, 3]")
        assert any("not an object" in e for e in result.errors)

    def test_the_raw_response_is_always_kept(self):
        """corpus/extracted/ is raw pipeline output (rule 8), including failures."""
        for raw in ["not json", "{}", json.dumps(contract())]:
            assert extract.parse("d1", "contract", raw).raw == raw


class TestPrompt:
    def test_it_renders_with_every_placeholder(self):
        bundle = load_extract_prompt()
        rendered = bundle.render(
            doc_type="contract",
            doc_id="contract-sup-04-20251018",
            json_schema=extract.SCHEMAS["contract"],
            document="## AMENDMENT",
        )
        assert "contract-sup-04-20251018" in rendered
        assert "## AMENDMENT" in rendered

    def test_a_missing_placeholder_says_which_one(self):
        with pytest.raises(KeyError, match="doc_id"):
            load_extract_prompt().render(
                doc_type="contract", json_schema="{}", document="x"
            )

    def test_the_document_sits_below_every_instruction(self):
        """Rule 6: retrieved text never lands in the instruction position."""
        bundle = load_extract_prompt()
        template = bundle.template
        assert template.index("# Security") < template.index("{document}")
        assert template.index("# Schema") < template.index("{document}")

    def test_the_clause_vocabulary_shown_matches_the_one_enforced(self):
        """A schema the model is shown that drifts from the gate it is judged by
        would fail every document for a reason the prompt never mentioned."""
        shown = extract.SCHEMAS["contract"]
        for name in extract.CLAUSE_VOCABULARY:
            assert name in shown

    def test_the_fingerprint_does_not_cover_the_database_context(self):
        """Extraction must not be re-run because business_context.md changed.

        The SQL prompt injects business_context.md and schema.md; this one
        injects neither, so the corrections gated in HANDOFF.md cost no extracted
        documents. If someone adds them, this fails and the cost becomes a
        decision instead of a surprise.
        """
        bundle = load_extract_prompt()
        assert set(bundle.hashes) == {"extract.md"}
        assert bundle_fingerprint(bundle.hashes)


class TestRunner:
    def test_the_stub_refuses_to_target_the_committed_corpus(self):
        """Stub answers are invented, and a file of them is indistinguishable
        from a real extraction once it is sitting in corpus/extracted/.

        This points `out` at the canonical directory on purpose. An earlier
        version passed tmp_path, which meant the out-of-place check was what
        made it pass and the stub guard was never exercised at all — a probe
        that could not fail, which is the class this repo keeps finding.
        """
        canonical = corpus_extract.CORPUS / "extracted"
        before = sorted(canonical.glob("*.json")) if canonical.is_dir() else []

        assert corpus_extract.run(argparse_namespace(provider="stub", out=None)) == 1

        after = sorted(canonical.glob("*.json")) if canonical.is_dir() else []
        assert after == before, "the stub wrote into corpus/extracted/"
        assert not (corpus_extract.CORPUS / "EXTRACT.csv").exists()

    def test_it_writes_one_file_per_document(self, tmp_path):
        corpus_extract.run(argparse_namespace(provider="stub", out=str(tmp_path)))
        manifest = corpus_extract.load_manifest(corpus_extract.CORPUS)
        assert len(list(tmp_path.glob("*.json"))) == len(manifest)

    def test_an_unparseable_response_still_writes_a_file(self, tmp_path):
        """The pipeline failing in the open is a result; a gap is not."""
        corpus_extract.run(argparse_namespace(provider="stub", out=str(tmp_path)))
        first = corpus_extract.load_manifest(corpus_extract.CORPUS)[0]["doc_id"]
        written = tmp_path / f"{first}.json"
        assert written.exists()
        assert extract.parse(first, "catalog", written.read_text()).data is None

    def test_output_has_no_crlf(self, tmp_path):
        """The defect the parse step shipped with, checked here before it ships."""
        corpus_extract.run(argparse_namespace(provider="stub", out=str(tmp_path)))
        offenders = [
            p.name for p in tmp_path.glob("*.json") if b"\r\n" in p.read_bytes()
        ]
        assert not offenders

    def test_record_count_reads_each_type_by_its_own_key(self):
        assert corpus_extract.record_count("contract", {"clauses": [1, 2]}) == 2
        assert corpus_extract.record_count("invoice", {"line_items": [1]}) == 1
        assert corpus_extract.record_count("policy", None) == 0


def argparse_namespace(**overrides):
    import argparse

    defaults = {
        "provider": "stub",
        "corpus": str(corpus_extract.CORPUS),
        "out": None,
        "only": "",
        "limit": 0,
        "no_cache": True,
        "max_calls": 60,
        "max_spend": 2.00,
    }
    return argparse.Namespace(**(defaults | overrides))
