# contract-sup-01-20241130 — supplier identity lost to OCR

**Extracted:** `supplier_code: null`, `supplier_name: "Kir   (-t) r i   () l i le."`
**True:** `SUP-01`, `Sahyadri Agro Traders`

**The pipeline got this wrong**, and it is the only header field wrong in the
whole run — 198 of 199 correct, and this is the one.

This is the `scanned-200dpi-skewed` document: rasterised, rotated a fraction of a
degree, blurred, speckled, JPEG'd, no text layer. The clause body OCRs cleanly and
**every number in it is exact** — payment terms 14, lead time 10, minimum order
8000, volume discount 0, returns window 14, and both period dates. The letterhead
does not survive.

**Not fixable by prompt.** The pixels do not contain readable text.

## Decided 2026-08-13: the fallback lives in the loader, not in extraction

The question was whether identity may fall back to `MANIFEST.csv`, resolving this
in every case at the cost of the claim that extraction records what the document
says. **Both, and the two are not in tension once they are put in different
places.**

- **`corpus/extracted/` is untouched.** `supplier_code` stays `null` and
  `supplier_name` stays `"Kir   (-t) r i   () l i le."`. That is what the
  document says, it is what the pipeline read, and rule 8 keeps it raw. Anyone
  measuring extraction is measuring extraction.
- **`embed_corpus.py` resolves identity from provenance when it loads.**
  `data.get("supplier_code") or supplier_code_for(doc_id)` — the manifest and the
  document id are legitimate knowledge about *where the file came from*, and
  using them to link a row is not the same as claiming the document stated them.
  **If both are missing the row is skipped rather than guessed.**

So the extraction score keeps counting this as the miss it is — it is the single
header field wrong in 198 of 199 — while retrieval and the clause table still
resolve the supplier correctly. A fallback inside extraction would have hidden
the defect by fixing it; a fallback in the loader records it and works anyway.

**The general rule this sets:** provenance may inform linkage, never content. The
loader knows which file it opened; the extractor only knows what was in it.

**1 of the 5 scanned documents is affected.** The other four resolve their
supplier correctly.
