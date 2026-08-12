# ADR-0009: EXTRACT runs on Vertex AI, deviating from "free tier only"

Date: 2026-08-06
Status: Accepted

## Context

CLAUDE.md rule 2 says free tier everywhere, no paid frontier calls. That rule
exists so the working system does not depend on paid inference — so a reader
can clone the repo and run the thing.

Phase 2 runs schema-guided extraction over `corpus/`, which is **real personal
documents**. The Phase 2 plan already includes a PII scan whose output is a
decision to exclude a document from the public corpus or redact a field at
source.

That scan protects the repository. It does not protect what the model provider
receives, and those are two different exposures. A document excluded from
`corpus/` for carrying a home address still gets sent to Google in full if the
extraction call that produced its data ran on a free-tier key.

## What the terms actually say

Verified against Google's own pages on 2026-08-06 rather than taken from
summaries, because this is the entire basis for the decision.

**Gemini API free tier** — [ai.google.dev/gemini-api/terms](https://ai.google.dev/gemini-api/terms),
effective 2026-03-23, last updated 2026-04-28:

> "Google uses the content you submit to the Services and any generated
> responses to provide, improve, and develop Google products and services"

and, on the same page:

> "human reviewers may read, annotate, and process your API input and output."

The page states plainly: *"Do not submit sensitive, confidential, or personal
information to the Unpaid Services."*

**Gemini API paid tier**, same page:

> "Google doesn't use your prompts (including associated system instructions,
> cached content, and files such as images, videos, or documents) or responses
> to improve our products"

**Vertex AI**: Google Cloud states that customer data is not used to train its
foundation models, and that prompts and tuning data stay out of the foundation
model training corpus.

⚠️ **Caveat on that last point.** The canonical Service Specific Terms page
would not load; the confirmation above comes from Google Cloud documentation
and product pages rather than the contract itself. Before the first extraction
run over real documents, read the Service Specific Terms directly and confirm.
If they disagree with the above, this ADR is void and the decision reopens.

## Decision

Model roles split across two credentials, on data terms rather than rate limits.

| Role | Where | Tier | Why |
|---|---|---|---|
| `PLAN` | Gemini API, Flash (pinned version) | Free | Synthetic POS data. Nothing personal, nothing confidential. |
| `CLASSIFY` | Gemini API, Flash-Lite, or local Ollama if RAM allows | Free | Same. Local is preferred where it fits. |
| `EXTRACT` | **Vertex AI via service account** | **Paid** | Real personal documents. |

A GCP budget alert is configured **before the first Vertex call**, not after.

Mistral is documented as a fallback and deliberately **not wired**. A second
provider that is never exercised is a second thing to keep working; if Gemini's
free tier becomes unusable, wiring it is a small change made at that point.

## Why this does not break rule 2

Rule 2's purpose is that the *working system* — the thing a reader clones and
runs — must not require paid inference. That still holds:

- `docker compose up` runs in `DEMO_MODE` with cached trajectories. No key.
- The live path uses the reader's own free-tier Gemini key for `PLAN`.
- Extraction is a **one-time, author-side build step** whose output —
  `corpus/parsed/`, `corpus/extracted/` — is committed. Nobody re-runs it to
  use the project. `make ingest` exists for reproducibility, not for operation.

So the deviation buys better data terms for one build step and changes nothing
about what a reader needs. Spending a small amount once to avoid feeding
someone's home address into a training corpus is the rule being served, not
bent.

## Alternatives rejected

**Extraction on the free tier.** The cheapest option and the reason this ADR
exists. It sends documents that were deliberately excluded from a public
repository to a provider that says it trains on them and has humans read them.
The PII scan would be theatre.

**Local extraction only.** Attractive, and genuinely better on data terms since
nothing leaves the machine. Rejected as the *primary* path because extraction
quality is the number the README publishes, and pinning that to whatever model
fits in available RAM makes the headline result a function of the developer's
hardware. Revisit at the 16GB tier — ADR-0006 already notes a pinned local
model would strengthen the reproducibility claim too.

**Redact harder, then use the free tier.** Redaction good enough to make a
scanned invoice safe for a training corpus is a harder problem than the
extraction itself, and failure is silent.

## Cost control

- Budget alert on the GCP project before first use.
- Extraction is bounded: roughly 40 documents, run a handful of times while the
  schema settles.
- Every raw extraction is committed, so re-running is only ever a deliberate
  verification (`make ingest-verify`), never a step in using the project.
- `PIPELINE.json` pins the model string **and the serving location**, so a re-run
  is a re-run rather than a new experiment. **It does not pin temperature, and
  this line said it did until 2026-08-12:** the sampling parameters are deprecated
  and ignored on these models, so `PIPELINE.json` records
  `"sampling_parameters": null` with a note saying why. See ADR-0006's 2026-08-06
  amendment — a temperature sitting in a reproducibility claim is worse than none,
  because it looks like a control and is not one.

## What would flip it

- The Service Specific Terms not saying what the documentation says. Read them
  first.
- Free-tier terms changing to exclude training. Then the split loses its
  purpose and everything returns to free.
- Extraction quality at the local tier reaching parity, which removes the spend
  and improves the reproducibility claim at the same time.
