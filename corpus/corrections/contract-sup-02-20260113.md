# contract-sup-02-20260113 — `&amp;` in the supplier name

**Extracted:** `Godavari Grains &amp; Pulses`
**Database:** `Godavari Grains & Pulses`

**The pipeline was right and the corpus is wrong.** `&amp;` is in the rendered
PDF and therefore in `corpus/parsed/`. The model transcribed what it was given,
which is exactly what rule 6 and the clause-level provenance decision ask of it.
Scoring this as an extraction error would punish the pipeline for being faithful.

`corpus_generate.py` HTML-escapes supplier names. Two suppliers have `&` in
theirs — **SUP-02 Godavari Grains & Pulses** and **SUP-04 Deccan Oils &
Provisions** — and three parsed documents carry entities.

**Not fixed by regeneration**, deliberately: regenerating changes the PDFs, voids
the parse, the checksums and all 40 extractions, to correct five characters in a
field nothing queries. It rides along with the next deliberate corpus
regeneration or not at all.
