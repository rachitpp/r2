# ADR-0010: All model calls route through Vertex; the AI Studio free tier cannot carry a measurement

Date: 2026-08-07
Status: **Proposed — three preconditions unverified. Do not act on it until they are.**

## Context

ADR-0009 split model roles across two credentials on data-terms grounds: `PLAN`
and `CLASSIFY` on the Gemini API free tier, `EXTRACT` on Vertex. Two things
have since made that split wrong.

### The free tier cannot carry the measurement

Measured on 2026-08-07, from the `429` response body rather than from
documentation or a blog, because Google no longer publishes the numbers:

    metric  generativelanguage.googleapis.com/generate_content_free_tier_requests
    id      GenerateRequestsPerDayPerProjectPerModel-FreeTier
    value   20
    model   gemini-3.6-flash

**Twenty requests per day**, per project, per model. The Phase 1 measurement is
189 calls — a five-question staging rotation, 46×1, then 46×3 for cross-run
variance. That is **9.4 days of elapsed time**, during which the prompt cannot
change, because any edit invalidates every cached response and restarts the
clock.

That is not a measurement cadence. It is a measurement that cannot be iterated
on, which is worse than an expensive one.

### The obvious fix is a trap

The first instinct was to enable billing on the AI Studio key: the whole 189
calls is ~2.19M input tokens, about **$3.70** at `gemini-3.6-flash` rates of
$1.50/M in and $7.50/M out. Trivial.

It is also a trap, and the trap is documented. From
[ai.google.dev/gemini-api/docs/billing](https://ai.google.dev/gemini-api/docs/billing):

> "No, the Google Cloud Welcome credit or free trial credit can't be used
> towards the Gemini API or AI Studio."

> "Does the Google Cloud Free Trial apply to Gemini API usage? No, starting
> March 2026, Gemini API usage costs are specifically excluded from the $300
> Google Cloud Free Trial program."

So enabling billing on the AI Studio key charges a card while any Google Cloud
credit sits unused, and when credits expire or run out, **usage bills silently
to the payment method on file.** There is a documented trail of people
discovering this from an invoice.

## Decision

**Route every model call through Vertex — `PLAN`, `CLASSIFY` and `EXTRACT`, one
credential.** Keep the AI Studio key as a documented fallback, unused.

This is strictly better than ADR-0009's split on four counts:

1. **Data terms improve.** ADR-0009 accepted that `PLAN` prompts became
   training data because they only ever contain synthetic POS questions. On
   Vertex they do not. That was a tolerated cost and is now simply gone.
2. **One provider, one quota model, one credential** — instead of a split whose
   only justification was a data-terms boundary that Vertex removes.
3. **Vertex per-project quotas are far above 20/day**, so the measurement can
   be iterated rather than endured.
4. **Google Cloud credits may apply** — see the precondition below, because
   this one is *not* confirmed.

## ⚠️ Three preconditions, none of them verified

**This ADR is Proposed, not Accepted, and the reason is that none of the
following could be checked from this environment.** There is no `gcloud`, no
service account, no `GOOGLE_APPLICATION_CREDENTIALS`, and nothing GCP-shaped in
`.env` beyond the AI Studio key. The service account ADR-0009 assumed for
Phase 2 does not exist yet.

### 1. Whether credits actually cover Gemini on Vertex — UNCONFIRMED

The billing page quoted above is explicit about AI Studio and **silent about
Vertex**. The Free Trial page separately excludes *"Vertex AI's generative AI
partner models offered as managed services"* — partner models means Claude,
Llama and Mistral in Model Garden, not first-party Gemini, so first-party
Gemini is probably covered.

**Probably is not good enough for something that bills a card on failure.**
Confirm in the billing console that Vertex Gemini usage draws down credit
before running anything at volume. If it does not, this ADR's fourth advantage
disappears and the decision has to be re-argued on the other three.

### 2. Remaining credit and expiry — UNKNOWN

The 90-day clock runs from **signup, not first use**. If the account is not new,
the balance may already be zero and the trial already closed. The real number is
whatever the billing console says, not $300.

### 3. Model availability and the exact model string — UNCHECKED

`gemini-3.6-flash` must exist on Vertex in the chosen region, and its model
string must be pinned exactly. A string that differs between AI Studio and
Vertex, or a region where the model is absent, **breaks reproducibility
silently** — and ADR-0006 already reduced the reproducibility claim to a pinned
model string, so that string is now the whole claim.

### Also: Vertex was renamed

Vertex AI became **Gemini Enterprise Agent Platform** in May 2026. Console
navigation and documentation paths have moved; `cloud.google.com/vertex-ai/...`
now redirects to `docs.cloud.google.com/...` and the docs index is titled for
the new name. ADR-0009 says "Vertex" throughout and is not being rewritten,
because that is what it was called when the decision was made. Anyone following
its links should expect the new name.

## Spending controls, in place before the first call

- **`--max-calls`, default 250**, checked before every request. The runner stops
  itself rather than looping away.
- **`--max-spend`, default $25**, on an estimate from prompt length and token
  price.
- Cached responses survive a budget stop, so a resumed run costs only the
  remainder.
- A GCP budget alert as well, because an application-level ceiling cannot catch
  spend from outside the application.

Credits make a runaway loop free right up until they do not, and then it is a
card. The ceiling exists so a runaway is discovered in minutes.

## What does not change

Nothing else in the design relaxes because a credit balance appeared. Bounded
agent loops, precomputation at ingestion, local embeddings, permanent response
caching and prompt hashing are all good design independent of budget, and all
of them get *worse* if loosened. **The credits are a measurement budget with a
90-day fuse, not a change in what the system is.**

## What would flip it

- Credits proving not to cover Vertex Gemini, *and* the 20/day free tier being
  judged tolerable after all. That trades nine days for a few dollars.
- Vertex quotas turning out to be no better in practice.
- A local model at the 16GB tier reaching adequate quality, which would remove
  the spend and strengthen ADR-0006's reproducibility claim at once.
