# Known issues

What is wrong with this corpus, or weaker in it than it looks.

**`PLAN.md`'s done-condition 6 asks that this file be non-empty and says why that
is a weak check here: for a corpus we generated, flawless handling means the
injected difficulty was too gentle, not that the pipeline is good.** So the bar
for an entry is a defect someone would otherwise hit — not a list assembled to
satisfy the condition.

Entries 1 and 2 were found by measuring the corpus rather than by extracting from
it, which is worth saying: **no model has been run over these documents yet.**
Everything a real extraction pass finds gets added below.

---

## 1. There are no coverage gaps, so demo beat 2's harder half is undemonstrable

**Twelve suppliers, twenty-four contracts, two each — and every predecessor ends
on the exact day its successor begins.** Measured 2026-08-11 from `MANIFEST.csv`.

`PLAN.md`'s Phase 2 done-condition 4 requires that *"a query for a date inside a
known gap returns 'no document in force', distinct from 'not found'"*. **No such
date exists.** The only dates with nothing in force are before each supplier's
first contract — earliest 2023-09-07 — and that is a much weaker case, because
"before any contract existed" is hard to tell apart from "not found", which is
the whole distinction being demonstrated.

**`README.md` asserted the opposite until 2026-08-11**, saying a date with no
contract in force was "a real gap in the corpus rather than a staged one". That
described what `valid_period` permits, not what the generator produced. It is the
same shape as the `expected_on` schema comment and the `business_date`/`sold_at`
claim in `docs/HANDOFF.md`: **a document asserting a property the artifact does
not have.** Corrected in place rather than deleted, so the correction is visible.

**Fixing it means regenerating the corpus with a deliberate lapse for one or two
suppliers, and that must happen before any extraction is paid for** — regenerating
changes the documents, which changes the parse, which voids extracted output.
Open decision; see `docs/PROGRESS.md`.

> A partial substitute already exists and should not be mistaken for the same
> thing: **only SUP-01 has price catalogs**, so a price question about any other
> supplier is a genuine "not found". That exercises one side of the distinction.
> It does not exercise the other.

## 2. One amendment declares a clause "as varied" and does not vary it

`contract-sup-04-20251018` states:

    Clause 7 (Returns window), as varied — 28 days from receipt.

The agreement it varies, `contract-sup-04-20240122`, also says 28 days. **The
clause is restated identically under a heading announcing a change.**

The other amendment, `contract-sup-09-20250909`, varies all three of its clauses
genuinely (payment 30→60, lead time 11→10, returns 28→14), so this is one
document of two rather than a property of the generator's amendment template.

Whether it was intended is unknown, and it is being kept either way: real
amendments do restate unchanged clauses, and an extraction that reports clause 7
as stated is *correct*. What must not happen is a downstream step inferring "this
changed" from "this was listed". Flagged here so the gold set labels it
deliberately rather than someone treating it as an extraction error later.

## 3. Every hard case was chosen by us

The standing limitation, repeated from `README.md` because it belongs on any list
of what is wrong with this corpus: ten of the forty documents carry an injected
property, and **we picked all ten.** Where a real corpus would produce difficulty
nobody anticipated, this one cannot. Extraction numbers measured against it say
*the pipeline handles the failures we thought of*, which is a real result and a
weaker claim than surviving documents nobody designed.

## 4. The pipeline is untested on non-Latin scripts

`bilingual-mr-en` is defined, rendered, verified — and assigned to nothing. The
build environment has no Devanagari font, so the Marathi text rendered blank and
verification refused the run. Transliterating into Latin script would have
produced a document carrying the label without the difficulty.

**For a Maharashtra grocery chain this is a real gap.** Installing a Devanagari
font and putting the mark back on a contract closes it — and, like entry 1, it
means regenerating, so the two should be done together if they are done at all.

## 5. `PARSE.csv` cannot be byte-stable, because it records timings

It carries a `parse_seconds` column, so **`make ingest` produces a different
`PARSE.csv` on every run even when every parsed document is byte-identical.**

This is why `make ingest-verify` diffs `corpus/parsed/` and not the report, and
why `verify-parse` compares the markdown only. The checksum on `PARSE.csv` in
`CHECKSUMS.txt` verifies the committed copy has not been corrupted — it does not
and cannot assert reproducibility.

Worth knowing before someone treats a dirty `PARSE.csv` after `make ingest` as a
reproducibility failure. It is a timing column doing what timing columns do.

## 6. The PII scan here is vacuous and is not a result

Kept from `README.md` because it is exactly the kind of thing that reads as a
passed check in a summary. Generated documents carry no personal data unless a
generator writes it; the scan is a standing check that the generator never invents
anything person-like, and **a check that cannot fail is not evidence that it
passed.**
