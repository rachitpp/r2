# ADR-0006: Determinism asserted at the parse layer; extraction claimed honestly

Date: 2026-08-05
Status: Accepted

## Context

The corpus is fixed, public, and committed, so `make ingest` should be
reproducible and that reproducibility should be verifiable by a reviewer. The
naive version — run `make ingest` twice in CI and diff — cannot work: it requires
model calls, meaning quota consumption and an API key in secrets on a public repo.

## Decision

Split the claim by layer.

**In CI, every push, no secrets required:**
- `make verify-corpus` — SHA-256 every file in `parsed/` and `extracted/` against
  `corpus/CHECKSUMS.txt`. Catches partial commits, accidental edits, corruption.
- `make verify-parse` — actually re-run Docling on a committed 4-document sample
  and assert byte-identity. Docling is local with no network calls, so this is a
  real reproducibility assertion that costs nothing and needs no key. **The sample
  was three until 2026-08-11 and the fourth is the load-bearing one** — see the
  amendment below.

**Local, gated, before tagging:**
- `make ingest-verify` — re-run the full pipeline into a temp directory and diff.
  Record the last-verified date and commit SHA in the corpus README.

Pin the Docling version and the **stable model string** in
`corpus/PIPELINE.json`.

## The honest claim

**LLM extraction is not guaranteed byte-identical across runs.** Providers do
not promise it; batching and hardware nondeterminism break it, and a model
string can be silently updated underneath you.

So the README said, when this ADR was written:

> Deterministic parse layer, asserted in CI. Extraction layer pinned to a stable
> model string and verified reproducible as of <date> by re-running it. LLM
> inference is not guaranteed byte-stable across provider changes.

Not "fully deterministic pipeline."

**Both halves of that quote have since been narrowed, by the two amendments
below and the one dated 2026-08-11.** The temperature pin does not exist, the
parse claim needs an environment scope, and "verified reproducible as of <date>"
was carrying a literal blank date for a verification that had never run. The
current wording lives in the README's *Reproducibility* section; this block is
kept as what the ADR was written against.

### Amended 2026-08-06: there is no temperature left to pin

This ADR originally said "pinned model and temperature 0", and so did the README
quote above. **That mechanism no longer exists on the models this project uses.**

Google's release notes for 21 July 2026 deprecated the sampling parameters, and
the linked detail page is unambiguous about what "deprecated" means here:

> "temperature, top_p, and top_k are deprecated and ignored."

> "In future model generations, supplying these parameters returns an HTTP 400
> error."

So on `gemini-3.6-flash` and `gemini-3.5-flash-lite` they are **ignored today** —
a request carrying `temperature=0` succeeds and the setting does nothing. Google's
guidance is to steer determinism through system instructions and structured
outputs instead. Sending them anyway would be worse than useless: it would sit in
the code looking like a reproducibility control while having no effect, which is
exactly the kind of thing a reviewer is right to distrust.

**The claim is restated as:**

> Pinned stable model string **and serving location**; extraction
> reproducibility **measured empirically** rather than asserted from a sampling
> parameter.

### Amended again 2026-08-07: location is part of the pin

The model string alone does not identify what answers. Measured on Vertex:
`gemini-3.6-flash` serves from `location=global` and returns **404** in both
`us-central1` and `asia-south1`. String and location are independent variables,
and only one of them was being recorded.

That 404 is the *loud* failure and cost nothing. The dangerous version is a
region serving a different build behind the same string: it would surface as
unexplained model drift, look like nondeterminism, and be untraceable — because
the thing that changed was never written down.

So `corpus/PIPELINE.json` records `location` alongside `model` for every role,
and a result file that does not name both describes less than it appears to.

Nothing about the layer split changes. What changes is that "reproducible" stops
being a configuration claim and becomes a measurement: run `make ingest-verify`,
diff, record the date and commit SHA. That was always the stronger form — the
parameter was doing less work than it looked like even when it functioned.

Do not send `temperature`, `top_p` or `top_k`. `PIPELINE.json` records the model
string and the verification date, and no sampling parameters.

### Amended 2026-08-11: the claim holds within an environment, not across one

**"Deterministic parse layer, asserted in CI" is true within a platform and false
across one.** Measured by re-parsing the whole corpus on Windows against output
generated on Linux — same Docling 2.118.1, same pinned versions in
`PIPELINE.json`: **5 of the 40 documents parse differently.** Four are
heading-versus-paragraph flips. One, `invoice-sup-12-5436`, loses its table
entirely and parses to the bare word `Supplier` — the hardest table case is the
one that degrades. It is stable run-to-run on a single machine, so this is a
platform split rather than randomness.

**The check could not see it, and the sample was why.** `verify-parse` re-parsed
three documents that all happen to be platform-stable, so it passed on a machine
reproducing only 34 of 38. A sample that cannot fail is not a sample. Fixed by
adding `invoice-sup-12-5436` to it, which makes `verify-parse` **an environment
gate rather than a formality**: it now reads `3/4` on Windows and is expected to
pass only in the reference environment. Run it before trusting any `make ingest`
output, and do not read a failure on a new machine as a broken repo.

**The claim is restated once more:**

> Parse layer byte-identical **within a pinned environment**, asserted in CI on a
> 4-document sample that includes a document known to diverge. Not asserted across
> environments, where 5 of 40 documents are known to differ.

**The real fix is the one the seed layer already has.** `make seed-generate` runs
inside a digest-pinned `python:3.12-slim` precisely because libm and tzdata
differences move its output. The parse layer pins Docling's *version* and not its
*environment*, and `PIPELINE.json`'s `parse` block records no platform at all — so
a value the claim depends on is missing from the file this ADR says the claim is
scoped to. Pinning the parse environment the way the seed environment is pinned
would close it. CI runs one platform, so none of this is assertable there.

### What this does to ADR-0001's threshold 3

Threshold 3 is cross-run variance > 10%. With no temperature control, that number
now measures **the model's inherent nondeterminism**, not prompt instability.

It remains the right thing to measure — a demo that answers differently on the
third run is a problem whatever the cause — but it must not later be read as a
prompt-quality metric. A high figure means "this model is not stable enough to
demo on", not "the prompt is bad", and the two have different remedies: the
first is answered by ADR-0001's pre-committed query templates for the demo path,
the second by prompt work. Reading the first as the second would send the effort
somewhere it cannot help.

## Alternative rejected

Claiming end-to-end determinism, or running full ingestion in CI.

## Why

Overclaiming and having a reviewer catch it costs more than the honest version
gains. A scoped claim that is actually true and actually asserted is a stronger
artifact than a broad one that isn't.

## What would flip it

A provider offering a genuine determinism guarantee, or moving extraction to a
pinned local model where byte-stability can be asserted directly. The latter is
plausible at the 16GB RAM tier and would be worth revisiting.