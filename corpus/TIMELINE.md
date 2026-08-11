# Timeline

What was in force when, per supplier, and what the corpus can and cannot
demonstrate about it. Derived from `MANIFEST.csv` and checked against the parsed
documents by hand on 2026-08-11.

`api/tests/test_corpus_timeline.py` asserts that every document listed here
exists in the manifest with these dates, and that no manifest document is
missing from this file — because a timeline that quietly stops describing the
corpus is worse than no timeline, and this is a file people will edit by hand.

**Dates are half-open, `[from, to)`**, matching `supplier_terms.valid_period`. A
contract ending 2025-06-29 and the next beginning 2025-06-29 means the successor
is in force on that day, not both.

---

## ⚠️ Coverage is continuous — there are no gaps

**Twelve suppliers, twenty-four contracts, two each, and every predecessor ends
on the exact day its successor begins.** No supplier has a period with nothing in
force after its first contract starts.

The only dates with no contract in force are **before each supplier's first
contract**, the earliest being 2023-09-07. That is a real "no document in force"
state and it is a weak one: it is hard to distinguish from "not found", which is
the distinction demo beat 2 exists to demonstrate.

**`PLAN.md`'s Phase 2 done-condition 4 therefore cannot be satisfied as built.**
`README.md` claimed otherwise until 2026-08-11 — it described what the generator
permits rather than what it produced. See `KNOWN_ISSUES.md`, entry 1.

## Supplier terms

| Supplier | | In force from | Until | Document |
|---|---|---|---|---|
| SUP-01 | Sahyadri Agro Traders | 2024-11-30 | 2025-06-29 | `contract-sup-01-20241130` · scanned, signature block |
| | | 2025-06-29 | — | `contract-sup-01-20250629` |
| SUP-02 | Godavari Grains & Pulses | 2025-06-03 | 2026-01-13 | `contract-sup-02-20250603` |
| | | 2026-01-13 | — | `contract-sup-02-20260113` · scanned |
| SUP-03 | Gokul Dairy Distributors | 2024-07-26 | 2025-12-09 | `contract-sup-03-20240726` |
| | | 2025-12-09 | — | `contract-sup-03-20251209` |
| SUP-04 | Deccan Oils & Provisions | 2024-01-22 | 2025-10-18 | `contract-sup-04-20240122` |
| | | 2025-10-18 | — | `contract-sup-04-20251018` · **clause-level amendment** |
| SUP-05 | Bhusari Foods Pvt Ltd | 2025-01-03 | 2025-09-24 | `contract-sup-05-20250103` |
| | | 2025-09-24 | — | `contract-sup-05-20250924` |
| SUP-06 | Jhat Pat Foods | 2024-09-28 | 2025-12-09 | `contract-sup-06-20240928` |
| | | 2025-12-09 | — | `contract-sup-06-20251209` |
| SUP-07 | Nilgiri Beverage Company | 2024-01-18 | 2025-06-02 | `contract-sup-07-20240118` |
| | | 2025-06-02 | — | `contract-sup-07-20250602` |
| SUP-08 | Mithas Confectioners | 2024-09-05 | 2025-07-29 | `contract-sup-08-20240905` |
| | | 2025-07-29 | — | `contract-sup-08-20250729` |
| SUP-09 | Nirmal Home Products | 2024-02-12 | 2025-09-09 | `contract-sup-09-20240212` |
| | | 2025-09-09 | — | `contract-sup-09-20250909` · **clause-level amendment** |
| SUP-10 | Softwrap Paper Mills | 2025-01-12 | 2025-11-07 | `contract-sup-10-20250112` |
| | | 2025-11-07 | — | `contract-sup-10-20251107` |
| SUP-11 | Arogya Consumer Care | 2023-09-07 | 2025-07-13 | `contract-sup-11-20230907` |
| | | 2025-07-13 | — | `contract-sup-11-20250713` |
| SUP-12 | Deepmala Festive Supplies | 2024-08-12 | 2025-12-18 | `contract-sup-12-20240812` |
| | | 2025-12-18 | — | `contract-sup-12-20251218` |

### The two amendments state only what they vary

Both restate nothing else, which is the case the extraction schema is built
around — `corpus/extracted/` records the clauses a document *contains*, and what
was in force is computed from the chain rather than asked of the model.

| | Varies | From → to |
|---|---|---|
| **SUP-04** `20251018` | Clause 3 payment terms | Net 30 → **Net 60** |
| | Clause 4 lead time | 9 → **7 days** |
| | Clause 7 returns window | 28 → **28 days** — ⚠️ **declared "as varied" and unchanged**, see `KNOWN_ISSUES.md` entry 2 |
| **SUP-09** `20250909` | Clause 3 payment terms | Net 30 → **Net 60** |
| | Clause 4 lead time | 11 → **10 days** |
| | Clause 7 returns window | 28 → **14 days** |

Neither amendment restates clause 5 (minimum order) or clause 6 (volume
discount), so those carry forward from the agreement each varies.

## Best demo-beat-2 question, given the above

**"What are our payment terms with Deccan Oils, and what were they before the
renegotiation?"** SUP-04 is the strongest case: the current answer (Net 60) comes
from an amendment that states it, the prior answer (Net 30) comes from a document
the amendment does not restate, and the boundary is 2025-10-18. Getting the
"before" right requires reading the earlier agreement rather than the one in
force, which is exactly the behaviour the beat is meant to show.

## Price catalogs — SUP-01 only

| Effective | Document |
|---|---|
| 2025-04-01 | `catalog-sup-01-20250401` |
| 2025-11-03 | `catalog-sup-01-20251103` · table spans a page break |
| 2026-05-04 | `catalog-sup-01-20260504` |

Catalogs carry no end date: each supersedes the previous on its effective date.
**Only SUP-01 has catalogs at all**, so a price question about any other supplier
has no document behind it — a "not found", distinct from "no document in force".

## Policies

| Effective | Document | |
|---|---|---|
| 2025-01-01 | `policy-returns` | Goods return and credit note policy |
| 2025-06-15 | `policy-procurement-authority` | Procurement authority and approval limits |
| 2025-09-01 | `policy-cold-chain` | Cold chain and perishable handling · scanned |

Free-standing and open-ended — the only document type with no database row
behind it, so nothing cross-checks their content.

## Invoices

Point-in-time documents; they supersede nothing. Ten, spanning 2025-01-06 to
2026-06-30.

| Date | Document | |
|---|---|---|
| 2025-01-06 | `invoice-sup-12-5436` | table spans a page break |
| 2025-07-08 | `invoice-sup-06-1764` | |
| 2025-12-16 | `invoice-sup-03-14107` | |
| 2026-01-30 | `invoice-sup-05-9119` | |
| 2026-02-01 | `invoice-sup-06-14543` | scanned, signature block |
| 2026-02-02 | `invoice-sup-10-14562` | |
| 2026-04-19 | `invoice-sup-07-4672` | scanned |
| 2026-04-25 | `invoice-sup-10-15385` | |
| 2026-05-31 | `invoice-sup-03-10305` | |
| 2026-06-30 | `invoice-sup-01-5316` | totals printed above the line items |

The last invoice falls on `AS_OF_DATE` (2026-06-30), the anchor the whole project
treats as "today". Nothing in the corpus is dated after it.
