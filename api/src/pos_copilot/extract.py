"""Extraction schemas and validation for the document corpus.

Phase 2. One schema per document type, and a validator that says what is wrong
with a returned object rather than whether it "looks right".

**The clause model is narrow on purpose.** A supply agreement states five terms;
an amendment states only the ones it varies. Extraction records the clauses a
document *contains* — never the set in force, which is a property of the whole
chain and is computed from it. `contract-sup-04-20251018` varies clauses 3, 4 and
7 and restates nothing else, so a correct extraction of it holds three clauses,
not five.

Doing it the other way round — asking for a complete `supplier_terms` row per
document — would make the model perform the inheritance, and then a correct
inheritance and an invented value would be indistinguishable in the output. That
is the whole reason for the narrow shape; see `docs/PROGRESS.md` → amendments vs.
supersessions.

**Validation is structural, not semantic.** It checks that the object has the
declared shape and that its values are the right kind of thing. Whether the
values are *right* is the gold set's job, and that is measurement, not assertion
(ADR-0005).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

#: The five terms a supply agreement carries. These are the `supplier_terms`
#: column names, so an extracted clause maps to the database without a
#: translation table in between — and a clause name outside this set is a
#: validation error rather than a new column appearing by surprise.
CLAUSE_VOCABULARY = (
    "payment_terms_days",
    "lead_time_days",
    "min_order_value",
    "volume_discount_pct",
    "returns_window_days",
)

DOC_TYPES = ("contract", "invoice", "catalog", "policy")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def strip_json_fences(text: str) -> str:
    """Remove a markdown fence around a JSON payload, whatever its tag.

    `scoring.strip_fences` does the same job for SQL but only recognises an
    ```sql tag. Widening it would touch the measurement path for the sake of a
    different caller, so this stays here; merge them if a third caller appears.
    """
    cleaned = text.strip()
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", cleaned, re.S)
    if fence:
        return fence.group(1).strip()
    return cleaned


# ─── Schemas, as the prompt sees them ────────────────────────────────────────
#
# These strings are injected into extract.md's {json_schema} placeholder. They
# are written as annotated JSON rather than JSON Schema because that is what the
# model reads best, and because the authoritative check is validate() below —
# a schema the model is shown is guidance, and a schema the output is checked
# against is a gate. Keeping them in one file is what stops the two drifting.

_CONTRACT_SCHEMA = (
    """{
  "readable": true,
  "supplier_code": "SUP-04 style code, or null if not printed",
  "supplier_name": "as printed",
  "document_kind": "agreement | amendment",
  "effective_from": "YYYY-MM-DD",
  "effective_to": "YYYY-MM-DD, or null if it runs until further notice",
  "clauses": [
    {
      "clause": "one of the term names listed below",
      "clause_number": "as printed, e.g. \\"3\\", or null",
      "value": 60,
      "verbatim": "the sentence this value came from, copied exactly"
    }
  ]
}

`clause` must be exactly one of:

"""
    # Built from the vocabulary the validator enforces, so the list the model is
    # shown and the list its answer is checked against cannot drift apart.
    + "\n".join(f"  - {name}" for name in CLAUSE_VOCABULARY)
    + """

Include one entry in `clauses` for each term THIS document states. An amendment
that varies three clauses has three entries. Do not pad the list."""
)

_INVOICE_SCHEMA = """{
  "readable": true,
  "invoice_number": "as printed",
  "supplier_code": "SUP-04 style code, or null",
  "supplier_name": "as printed",
  "invoice_date": "YYYY-MM-DD",
  "purchase_order_ref": "as printed, or null",
  "currency": "INR",
  "subtotal": 12345.67,
  "tax_total": 0.00,
  "total": 12345.67,
  "line_items": [
    {
      "description": "as printed",
      "quantity": 12,
      "unit_price": 45.50,
      "line_total": 546.00
    }
  ]
}

Include every line item, including any that continue onto a second page. If the
totals are printed above the line items rather than below them, they are still
the totals."""

_CATALOG_SCHEMA = """{
  "readable": true,
  "supplier_code": "SUP-01 style code, or null",
  "supplier_name": "as printed",
  "effective_from": "YYYY-MM-DD",
  "currency": "INR",
  "prices": [
    {
      "product_name": "as printed",
      "product_code": "as printed, or null",
      "unit_price": 45.50,
      "case_pack": 12
    }
  ]
}"""

_POLICY_SCHEMA = """{
  "readable": true,
  "policy_name": "as printed",
  "effective_from": "YYYY-MM-DD, or null if undated",
  "rules": [
    {
      "heading": "the section heading this rule sits under",
      "statement": "the rule, in the document's own words"
    }
  ]
}

A policy has no database row behind it. Extract what it says; do not map it onto
supplier terms."""

SCHEMAS = {
    "contract": _CONTRACT_SCHEMA,
    "invoice": _INVOICE_SCHEMA,
    "catalog": _CATALOG_SCHEMA,
    "policy": _POLICY_SCHEMA,
}


@dataclass
class Extraction:
    """A parsed extraction plus everything wrong with it.

    `raw` is kept whatever happens, because `corpus/extracted/` is raw pipeline
    output (CLAUDE.md rule 8) and an unparseable response is a result — it is the
    pipeline failing in the open rather than quietly.
    """

    doc_id: str
    doc_type: str
    raw: str
    data: dict | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.errors


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _check_rows(rows: object, name: str, required: dict[str, str]) -> list[str]:
    """Validate a list of uniform records: `required` maps field -> kind."""
    if not isinstance(rows, list):
        return [f"{name} must be a list"]
    errors = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{name}[{index}] is not an object")
            continue
        for key, kind in required.items():
            if key not in row:
                errors.append(f"{name}[{index}] is missing {key}")
                continue
            value = row[key]
            if value is None:
                continue
            if kind == "number" and not _is_number(value):
                errors.append(f"{name}[{index}].{key} is not a number: {value!r}")
            if kind == "text" and not isinstance(value, str):
                errors.append(f"{name}[{index}].{key} is not text: {value!r}")
    return errors


def _check_date(value: object, name: str, *, required: bool) -> list[str]:
    if value is None:
        return [] if not required else [f"{name} is required"]
    if not isinstance(value, str) or not _DATE.match(value):
        return [f"{name} is not an ISO date: {value!r}"]
    return []


def validate(doc_type: str, data: dict) -> list[str]:
    """Structural errors in an extracted object. Empty list means well-formed.

    Not "correct" — well-formed. A contract naming a payment term of 9,000 days
    passes here and fails the gold set, which is the right division of labour:
    this runs on all 40 documents with no ground truth, and the gold set knows
    what the answers are.
    """
    errors: list[str] = []
    if doc_type not in SCHEMAS:
        return [f"unknown doc_type {doc_type!r}"]

    readable = data.get("readable")
    if not isinstance(readable, bool):
        errors.append("readable must be true or false")
    if readable is False:
        # An honest refusal. Everything else being null is the point of it, so
        # do not then complain that everything else is null.
        return errors

    if doc_type == "contract":
        kind = data.get("document_kind")
        if kind not in ("agreement", "amendment"):
            errors.append(f"document_kind must be agreement or amendment: {kind!r}")
        errors += _check_date(
            data.get("effective_from"), "effective_from", required=True
        )
        errors += _check_date(data.get("effective_to"), "effective_to", required=False)

        clauses = data.get("clauses")
        if not isinstance(clauses, list):
            errors.append("clauses must be a list")
        else:
            if not clauses:
                errors.append("clauses is empty — a contract states at least one term")
            errors += _check_rows(
                clauses,
                "clauses",
                {"clause": "text", "value": "number", "verbatim": "text"},
            )
            for index, row in enumerate(clauses):
                if isinstance(row, dict) and row.get("clause") not in CLAUSE_VOCABULARY:
                    errors.append(
                        f"clauses[{index}].clause is not a known term: "
                        f"{row.get('clause')!r}"
                    )
            seen = [r.get("clause") for r in clauses if isinstance(r, dict)]
            duplicates = sorted({c for c in seen if seen.count(c) > 1 and c})
            if duplicates:
                # One document stating the same term twice is either a parse
                # artifact or a real contradiction. Either way it is not
                # something to average.
                errors.append(
                    f"clauses states these terms more than once: {duplicates}"
                )

    elif doc_type == "invoice":
        # invoice_number, tax_total and total were required here until
        # 2026-08-12, and NOT ONE of the 40 generated invoices contains any of
        # them. The generator writes a PO number, a subtotal and a line-item
        # table; there is no invoice number, no tax line and no grand total in
        # the documents at all. So all 10 invoices failed validation on the
        # first real run while their content was extracted perfectly — 63/63
        # line items and 10/10 subtotals exact against the database.
        #
        # The schema was describing an invoice nobody generated. It survived
        # because the stub returns invented values that happen to include those
        # fields, so every test passed against a shape the corpus never had.
        #
        # Kept in the PROMPT deliberately rather than removed: asked for three
        # fields that do not exist, the model returned null for all three
        # instead of inventing plausible numbers. That is a live hallucination
        # check on absent fields, it passes 10/10, and removing it from the
        # prompt would both discard the check and void 40 cached responses.
        # Requiring them HERE is what was wrong.
        errors += _check_date(data.get("invoice_date"), "invoice_date", required=True)
        if not _is_number(data.get("subtotal")):
            errors.append(f"subtotal is not a number: {data.get('subtotal')!r}")
        for money in ("tax_total", "total"):
            value = data.get(money)
            if value is not None and not _is_number(value):
                errors.append(f"{money} is present but not a number: {value!r}")
        errors += _check_rows(
            data.get("line_items"),
            "line_items",
            {
                "description": "text",
                "quantity": "number",
                "unit_price": "number",
                "line_total": "number",
            },
        )

    elif doc_type == "catalog":
        errors += _check_date(
            data.get("effective_from"), "effective_from", required=True
        )
        errors += _check_rows(
            data.get("prices"),
            "prices",
            {"product_name": "text", "unit_price": "number"},
        )

    elif doc_type == "policy":
        if not data.get("policy_name"):
            errors.append("policy_name is required")
        errors += _check_date(
            data.get("effective_from"), "effective_from", required=False
        )
        errors += _check_rows(
            data.get("rules"), "rules", {"heading": "text", "statement": "text"}
        )

    return errors


def parse(doc_id: str, doc_type: str, raw: str) -> Extraction:
    """Fence-strip, parse, validate. Never raises — a bad response is a result."""
    payload = strip_json_fences(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return Extraction(doc_id, doc_type, raw, None, [f"response is not JSON: {exc}"])
    if not isinstance(data, dict):
        return Extraction(
            doc_id,
            doc_type,
            raw,
            None,
            [f"response is a {type(data).__name__}, not an object"],
        )
    return Extraction(doc_id, doc_type, raw, data, validate(doc_type, data))


def reconciles(data: dict, tolerance: float = 0.01) -> bool | None:
    """Whether an invoice's line items sum to its subtotal.

    None when the check cannot run. This is the one place the corpus gives a
    free correctness signal with no gold label: `corpus/README.md` notes invoice
    totals reconcile against `sum(line_total)` by construction, so a
    mis-extracted line item is detectable rather than merely wrong.
    """
    subtotal = data.get("subtotal")
    rows = data.get("line_items")
    if not _is_number(subtotal) or not isinstance(rows, list) or not rows:
        return None
    total = 0.0
    for row in rows:
        if not isinstance(row, dict) or not _is_number(row.get("line_total")):
            return None
        total += float(row["line_total"])
    return abs(total - float(subtotal)) <= tolerance
