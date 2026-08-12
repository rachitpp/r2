# The two clause-level amendments cannot be scored against `supplier_terms`

`contract-sup-04-20251018` and `contract-sup-09-20250909` are the corpus's two
`clause-level-amendment` documents. Each varies three clauses and restates
nothing else:

    ## Clause 3 (Payment terms), as varied
    ## Clause 4 (Lead time), as varied
    ## Clause 7 (Returns window), as varied

Both extractions returned exactly those three clauses and `null` for minimum
order value and volume discount. **That is correct — the documents do not
contain them.**

The gold set is derived from `supplier_terms`, which is a **wide table that
supersedes as a set**, so its row carries the full inherited set of clauses. Every
clause the amendment deliberately does not restate therefore reads as a miss, and
what is being measured is the inheritance rather than the extraction.

**This is the case the clause-level provenance decision was made for**, and it is
the first time the corpus has demonstrated it rather than the argument asserting
it. Scoring these properly needs `supplier_term_clauses` — a narrow table of what
each document *says*, with `supplier_terms` kept as the queryable projection —
which is Phase 3 work, where retrieval queries it.

**Until then both documents are excluded from header scoring** and the count is
printed, so the exclusion is visible rather than silently reducing the
denominator. `AMENDMENTS` in `api/scripts/eval_extraction.py`.
