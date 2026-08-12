# Corrections

`corpus/extracted/` is raw pipeline output and is never hand-edited (CLAUDE.md
rule 8). Where the extraction and the database disagree, the disagreement is
recorded here with a note saying **which side was wrong** — and that is not
always the pipeline.

Four entries, from the first extraction run (2026-08-12). **Two of them say the
pipeline was right**, which is worth stating plainly: a corrections directory
that only ever blames the model is not recording what happened.

| File | Who was wrong |
|---|---|
| `contract-sup-01-20241130.md` | The pipeline — OCR lost the letterhead |
| `contract-sup-02-20260113.md` | **The corpus** — `&amp;` is in the PDF |
| `catalog-supplier-code.md` | The pipeline — inferred a code no catalog prints |
| `clause-level-amendments.md` | **Neither** — the gold set cannot score these |

None of these is applied to `corpus/extracted/`. They are notes about it.
