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

**Not fixable by prompt.** The pixels do not contain readable text. The fix would
be to let identity fall back to `MANIFEST.csv`, which resolves it in every case
and weakens the claim that extraction records what the document says. That is an
open decision, not an oversight.

**1 of the 5 scanned documents is affected.** The other four resolve their
supplier correctly.
