# Catalogs — a supplier code that is not in any catalog

**No catalog prints a supplier code.** Measured: all three contain zero
occurrences of `SUP-`. They head with `PRICE LIST - Sahyadri Agro Traders -
November 2025` and nothing else identifying.

Two of the three extractions returned `supplier_code: "SUP-01"` anyway, inferred
from the supplier name. One returned `null`.

**The two that "succeeded" were guessing, and the honest one looked like a
failure.** Until 2026-08-12 the scorer counted `supplier_code` as a catalog
header field, so it scored the two inferences CORRECT and the refusal as a MISS
— **rewarding the hallucination and penalising the refusal**, which inverts the
thing this project exists to measure.

The inference is correct here, and that is what makes it dangerous: it is right
because there is one catalog supplier in this corpus, not because it was read off
the page. With a second supplier issuing catalogs it would be a coin flip
presented as a fact.

**Fixed in the scorer**, not in the output: `supplier_code` is no longer a scored
catalog field. The extracted values stay as they are, because they are what the
pipeline produced.
