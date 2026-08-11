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

## 1. RESOLVED 2026-08-11 — the corpus had no coverage gaps for two weeks

**Kept because the fix is less interesting than how the claim survived.**

`README.md` said a date with no contract in force was *"a real gap in the corpus
rather than a staged one"*. It described what `valid_period` **permits**, not what
the generator **produced**. Measured from `MANIFEST.csv`: twelve suppliers,
twenty-four contracts, and every predecessor ending on the exact day its successor
began. Zero gaps — so `PLAN.md`'s done-condition 4, *"a query for a date inside a
known gap returns 'no document in force', distinct from 'not found'"*, had nothing
to query, and demo beat 2's harder half was undemonstrable.

Same shape as the `expected_on` schema comment and the `business_date`/`sold_at`
claim in `docs/HANDOFF.md`: **a document asserting a property the artifact does
not have.** It survived because nothing compared the sentence to the data.

**Fixed** by regenerating the seed with `LAPSED_SUPPLIERS` in
`api/scripts/seed.py`: SUP-06 lapses 48 days (2025-10-22 → 2025-12-09) and SUP-11
lapses 78 days (2025-04-26 → 2025-07-13). Drawn from their own RNG substream, so
one field in one row per supplier moved and nothing else in the seed did.

Three things worth keeping from the fix:

- **The first attempt was wrong and a guard caught it.** SUP-03 and SUP-07 were
  chosen first; `make eval-expectations` refused to write because q014 asks for
  Nilgiri Beverage Company's terms in March 2025 and SUP-07's new lapse covered
  that date, so the reference query correctly returned nothing. An empty
  expectation scores every wrong answer as correct. SUP-06 and SUP-11 are the only
  two suppliers no eval question names, established mechanically rather than by eye.
- **Two expected result sets legitimately moved** — q017 and q048, both of which
  read `supplier_terms` by period, and only for the two lapsed suppliers.
- **`api/tests/test_corpus_timeline.py` now asserts the lapses exist**, with the
  dates pinned. The earlier version asserted the opposite and failed the moment
  the seed changed, naming the three documents that had to change with it. That is
  the behaviour worth having: the corpus and its documentation move together, or
  the build stops.

> One side of the distinction was already available and should not be confused
> with the other: **only SUP-01 has price catalogs**, so a price question about any
> other supplier is a genuine "not found".

## 2. The Docling parse is platform-dependent, and two parses are stale

**ADR-0006 says "Deterministic parse layer, asserted in CI". That is true within a
platform and false across one.** Measured 2026-08-11 by re-parsing the whole
corpus on Windows against output generated on Linux, same Docling 2.118.1, same
pinned versions in `PIPELINE.json`:

- **5 of the 40 documents parse differently.** The first count published here was
  4 of 38, and it undercounted for an instructive reason: the two documents whose
  PDFs had just been regenerated were excluded from the comparison because there
  was nothing to compare them against. Parsing their *previous* PDFs on Windows
  and diffing against the committed output put `contract-sup-11-20230907` in the
  divergent set too. **A sample that silently excludes the cases you changed is
  not measuring the population you think it is.**
- Four are heading-versus-paragraph flips, in both directions
  (`contract-sup-03-20240726`, `contract-sup-04-20240122`,
  `contract-sup-08-20250729`, `contract-sup-11-20230907`).
- **One loses a table.** `invoice-sup-12-5436` — the document carrying
  `table-spans-page-break` — parsed to a markdown table on Linux and to the bare
  word `Supplier` on Windows. The hardest table case is the one that degrades.
- It is **stable run-to-run on a single machine**: re-parsing on Windows twice
  gives identical output. This is a platform split, not randomness.

**`verify-parse` could not see this, and its sample was why.** It re-parsed three
documents and all three happen to be platform-stable, so the check passed on a
machine that reproduced only 34 of 38 — the recurring class, in a check written
the same day.

**Fixed by adding `invoice-sup-12-5436` to the sample**, the document that does
diverge. `verify-parse` now fails on Windows (`3/4 matched`) and is expected to
pass only in the reference environment, which makes it an environment gate rather
than a formality: **run it before trusting any `make ingest` output.** A sample
that cannot fail is not a sample.

**The real fix is the one the seed layer already has:** `make seed-generate` runs
inside a digest-pinned `python:3.12-slim` precisely because libm and tzdata
differences move its output. The parse layer pins Docling's *version* and not its
*environment*, so ADR-0006's claim should be scoped to "within a pinned
environment" and the parse should run in one.

> ### Two documents carry a Windows parse, one of them imperfectly
>
> `contract-sup-06-20240928` and `contract-sup-11-20230907` had their PDFs
> regenerated for the coverage lapses, so their parses had to be redone. **This
> was necessary rather than cosmetic:** until it was, the lapse existed in the
> database, the manifest and the PDF but *not* in `corpus/parsed/` — the layer
> extraction reads and Phase 3 will embed. A document-grounded question would have
> answered that coverage was continuous, which is precisely the thing
> done-condition 4 exists to disprove.
>
> Both were re-parsed on Windows, with the platform cost measured first rather
> than assumed:
>
> - **`contract-sup-06-20240928` is faithful.** Parsing its previous PDF here
>   reproduced the committed output byte for byte, so this machine handles that
>   document correctly.
> - **`contract-sup-11-20230907` is not.** Its line 3 loses the `##` heading
>   marker, exactly as the same test predicted. Twenty-three other contracts carry
>   that line as a heading; this one now does not.
>
> **The dates — the thing the lapse depends on — are correct in both.** What is
> wrong is one structural marker in one file.
>
> **Owed: a `make ingest` on the environment that produced the original parse**
> (the codespace, not a Windows checkout), which restores SUP-11's heading and
> puts the whole corpus back on one provenance:
>
>     cd api && uv sync --all-groups && cd ..
>     make verify-parse        # MUST pass — this is what proves the environment
>     make ingest
>
> **Run `verify-parse` first and do not skip it.** It is the only thing separating
> "this machine reproduces the reference parse" from "this machine produced
> something plausible", and it now includes a document that can fail. `PARSE.csv`
> will show changed timings for all 40; that is entry 6, not a problem.

## 3. One amendment declares a clause "as varied" and does not vary it

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

## 4. Every hard case was chosen by us

The standing limitation, repeated from `README.md` because it belongs on any list
of what is wrong with this corpus: ten of the forty documents carry an injected
property, and **we picked all ten.** Where a real corpus would produce difficulty
nobody anticipated, this one cannot. Extraction numbers measured against it say
*the pipeline handles the failures we thought of*, which is a real result and a
weaker claim than surviving documents nobody designed.

## 5. The pipeline is untested on non-Latin scripts

`bilingual-mr-en` is defined, rendered, verified — and assigned to nothing. The
build environment has no Devanagari font, so the Marathi text rendered blank and
verification refused the run. Transliterating into Latin script would have
produced a document carrying the label without the difficulty.

**For a Maharashtra grocery chain this is a real gap.** Installing a Devanagari
font and putting the mark back on a contract closes it — and, like entry 1, it
means regenerating, so the two should be done together if they are done at all.

## 6. `PARSE.csv` cannot be byte-stable, because it records timings

It carries a `parse_seconds` column, so **`make ingest` produces a different
`PARSE.csv` on every run even when every parsed document is byte-identical.**

This is why `make ingest-verify` diffs `corpus/parsed/` and not the report, and
why `verify-parse` compares the markdown only. The checksum on `PARSE.csv` in
`CHECKSUMS.txt` verifies the committed copy has not been corrupted — it does not
and cannot assert reproducibility.

Worth knowing before someone treats a dirty `PARSE.csv` after `make ingest` as a
reproducibility failure. It is a timing column doing what timing columns do.

## 7. The PII scan here is vacuous and is not a result

Kept from `README.md` because it is exactly the kind of thing that reads as a
passed check in a summary. Generated documents carry no personal data unless a
generator writes it; the scan is a standing check that the generator never invents
anything person-like, and **a check that cannot fail is not evidence that it
passed.**
