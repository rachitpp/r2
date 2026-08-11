# Progress

**Read this first. Write it last.** This is the only memory across sessions.

Keep it short. Delete resolved items rather than accumulating history — git has
the history. This file answers one question: what does the next session need?

---

## Current phase

**Phase 2 — Corpus ingestion. IN PROGRESS. The corpus exists and is parsed;
extraction is not built, and that is the gate.**

Phase 1 closed 2026-08-09 and the reasoning for closing it is kept below, because
it is what the eval numbers in the README rest on.

**Where Phase 2 stands against `PLAN.md`'s seven done-conditions:** two hold
(reproducible parse asserted in CI, and the PII scan recorded honestly as
vacuous). Five do not: no extraction, no gold set, no `TIMELINE.md`, no injection
specimen, no `KNOWN_ISSUES.md`, and the README's four-number block is still blank.

- **Corpus: done.** 40 synthetic documents generated from the seeded database —
  24 contracts (including 2 clause-level amendments), 10 invoices, 3 catalogs,
  3 policies. 10 carry an injected difficulty, each re-derived from the rendered
  PDF before the manifest is written. Byte-identical on regeneration.
- **Parse: done, and now actually checked.** All 40 parsed with Docling into
  `corpus/parsed/` with `PARSE.csv`. `verify-parse` re-parses a 3-document sample
  and asserts byte-identity in CI — see *Last session*, because until 2026-08-11
  it was a stub that could only fail.
- **Extraction: not started.** No prompt, no schema, no `corpus/extracted/`.

**Two decisions of yours gate the first extraction run** and are unchanged in the
open-questions list below: data residency for `location=global`, and the
canonical Vertex terms. A third — amendments vs. supersessions — is now *decidable*
rather than blocked, because the corpus contains 2 clause-level amendments by
construction.

### Why Phase 1 was closed the way it was — kept, because the README rests on it

`docs/PLAN.md` says Phase 1 is done when the harness prints execution accuracy,
silent-wrong and cross-run variance **and** a question asked in the web app
returns an answer beside the query that produced it. Both hold, and the second was
re-verified end to end after the last change.

**Why it is being closed with known defects open rather than kept open until they
are gone.** Three consecutive sessions went into the instrument, ~$9.83 and 447
model calls, against a phase budgeted ~32h that is at a large multiple of it. The
deliverable has been working for two days. Everything still open is instrument
refinement whose value is now clearly diminishing: the last full measurement cycle
bought one genuine finding (the timeout idiom) and one retraction of my own. The
budget rule in `HANDOFF.md` says to check this **at the point where it can still
change what you do** — this is that point, and what it changes is: stop measuring.

**What is NOT being claimed by closing it:** that the eval is clean. Threshold 1
fires, five questions produce unstable silent-wrongs, and two documented blind
spots (`is_active`, `business_date`/`sold_at`) cannot be detected by the instrument
at all. All of it is carried below as named debt, none of it blocks Phase 2.

- **Harness: done, and measured six times** — three triples of the current
  prompt and three of the previous one. **The samples disagree with each other in
  ways that decide things**, which was that session's main finding; the six-sample
  table is in `docs/HANDOFF.md`. Quote the clean triple (runs 3–5 of `f3b7a9…`)
  and nothing else.
- **Web app: the query view exists and works.** `web/` is a Next.js App Router
  app with the proposed palette and type in `tailwind.config.ts`, a typed client
  mirroring the FastAPI models, and the answer-beside-SQL view. `make web` with
  `make serve` alongside. **Demo beat 1 runs end to end.**
  The approval card (the design plan's signature surface) is Phase 4 and is not
  built. `docs/DESIGN-TOKENS.md` was proposed and then built from — say if the
  palette or type should change and it is a config edit, not a rewrite.
- **Live model path: built, opt-in, and proven against the real model.**
  `DEMO_MODE=false` (`make serve-live`) generates the SQL instead of reading it
  from a file. Every branch is exercised against a stub in CI — no key, no quota —
  and three real Vertex calls (~$0.06) confirmed an answer, a refusal and a
  clerk-scoped query end to end.

**ADR-0001 is resolved — keep generated SQL — but do not cite "two thresholds
fired" any more.** Threshold 3's firing at 10.6% was a sampling artifact: a strict
replication of the same prompt and questions returned 4.3%, and the metric has no
fixed value until the run count is fixed. The resolution's conclusion survives; two
of its three reasons do not. **The canned demo path is still load-bearing** for the
part that does survive, so the live path was added beside it and did not replace it.
Read the ADR's *Review* and *Replication* sections before quoting any of it.

State and corrections: `docs/HANDOFF.md`. Fix-list history:
`evals/FIX-LIST-v2.md`.

## Where things stand

| Phase | Status | Note |
|---|---|---|
| 0 Data foundation | **done** | ~32h against a 20h budget |
| 1 Structured Q&A | **closed 2026-08-09** | Both halves done and demo beat 1 re-verified; live path proven. Measured six times; ADR-0001's thresholds resolved (3 retired, 1 fires on five *unstable* questions). Closed with known instrument debt, listed below — none of it blocks Phase 2. ~$9.83 and 447 calls across three sessions, against a phase budgeted ~32h |
| 2 Corpus ingestion | **in progress** | Corpus generated (40 documents) and parsed; both reproducible and asserted. Extraction not started, and it is the gate. 2 of 7 done-conditions hold. Data residency for `location=global` still unanswered and still blocks the first run |
| 3 Document Q&A | not started | |
| 4 Procurement agent | not started | |
| 5 Polish | not started | |

## Last session

_Date:_ 2026-08-11
_What landed:_ The environment stood up on Windows, and **four checks that were
not running turned out to be wearing the label of checks that were.** No model
calls, no spend.

### The parse layer was never actually verified

- **`verify-parse` was a stub that could only fail.** It skipped while
  `corpus/parsed/` was absent and printed `not implemented; exit 1` once it was
  not — so **CI has been red on master since the parse landed**, on the last step
  of the run. It now does what ADR-0006 specifies: re-parses a 3-document sample
  and asserts byte-identity, with a counter so it cannot confuse "found no
  differences" with "compared nothing".
- **`make ingest-verify` has never once executed its comparison.** The final
  progress line called `Path.relative_to(REPO_ROOT)`, which raises whenever
  `--out` points outside the repo — which is exactly what the target passes
  (`mktemp -d`). It crashed *after* the full parse, and the Makefile's `&&` meant
  the diff never ran. ADR-0006's reproducibility assertion was unfalsifiable by
  construction, the same shape as ADR-0001's reversal test.
- **`--only` truncated `PARSE.csv` from 40 rows to 1**, so the report then
  claimed the corpus held one document. Found by running it.
- **`PARSE.csv` recorded hashes that no file on disk had.** `write_text` with no
  explicit `newline` translates every newline on Windows, while the `sha256`
  beside it is taken over the in-memory string. `verify-corpus` cannot catch it
  either, because `parsed/` is not in `CHECKSUMS.txt` — see *Named debt*.

**Each fix carries an assertion, and each assertion was validated by
reintroducing the defect and watching it fail** — `api/tests/test_corpus_ingest.py`,
the first corpus tests in the repo. Instance eight's lesson, applied on the way in
rather than after.

### The parse is deterministic across platforms — measured, not assumed

The 3-document sample re-parsed on **Windows** is byte-identical to output
generated in a **Linux** codespace, OCR included, on a 200dpi skewed scan with no
text layer. ADR-0006 scopes the determinism claim to the parse layer; this is the
first evidence that the scope holds across machines rather than only across runs.

### Two things a fresh clone trips over, neither of them in the repo

- **`core.autocrlf=true` and no `.gitattributes` breaks every hash in the
  project.** On Windows this failed two tests with confidently wrong messages —
  "prompt changed since the freeze" and "49 expectations computed against a
  different seed". Neither was true: LF-normalising the bytes reproduces
  `PROMPT_FREEZE.json` and the seed fingerprint exactly. Fixed for this clone with
  `core.autocrlf=false` and a re-checkout. **A committed `.gitattributes` is the
  durable fix and has not been written** — it is a repo-wide decision.
- **`make ingest` needs two environment variables on Windows** and nothing says
  so: `HF_HUB_DISABLE_SYMLINKS=1` (hf_hub symlinks need admin or Developer Mode)
  and `TORCHDYNAMO_DISABLE=1` (TorchInductor shells out to MSVC `cl.exe`). Both
  are no-ops on Linux and in CI. Where they belong — `.env.example`, the corpus
  README, or the Makefile — is not decided.

### The state documents had gone stale, which is the defect this project names

`CLAUDE.md`, `README.md`, `PROGRESS.md` and `HANDOFF.md` all still said the corpus
did not exist, **two commits after it was generated and parsed.** `HANDOFF.md`
exists in the repo precisely so a stale state document can be corrected — and it
is the one pasted into a new session first. Being version-controlled made it
correctable; it did not make it correct. All four are reconciled in this session.

_The 2026-08-09 eval findings — six samples, threshold 3 retired, q017 and q036
fixed, q049 withdrawn — are preserved in `docs/HANDOFF.md` and in **Measured
numbers** below. They have not changed._

_What didn't:_ extraction, which is Phase 2's actual deliverable. `parsed/` is
still absent from `CHECKSUMS.txt`.
_Anything half-finished someone would trip over:_ No.
_Is the system in a working state?_ Yes. 207 passed, 33 skipped without a
database; ruff clean; `make web-check` clean; `verify-corpus` and `verify-parse`
both pass.


## Next session should

**Phase 1 is closed. Do not reopen the eval to chase the remaining items** — they
are listed under *Named debt* and each is cheap to do **inside** a later phase that
touches the prompt anyway. Reopening it on its own is what the last three sessions
did, at ~$9.83 and diminishing returns.

**The corpus is no longer the blocker. Extraction is, and one decision of yours
gates it:** data residency, because Vertex serves this model from
`location=global` only, so the first extraction run sends document content to an
unpinned region. The corpus being synthetic weakens that question a great deal —
nothing in it is confidential — but it was never formally closed, and the second
half of it has not weakened at all: **the canonical Vertex terms**, which
ADR-0009 rests on and which have still only been confirmed from documentation
rather than the terms themselves. That page is client-rendered and **needs a
browser, not a fetcher**; look for the "Zero Data Retention" section.

In value order:

1. **Decide amendments vs. supersessions.** It is now decidable rather than
   blocked: the corpus contains 2 clause-level amendments by construction
   (`PLAN.md` says generate both shapes, and it did). If they are to be modelled
   as amendments, the answer is a narrow `supplier_term_clauses` table for
   clause-level provenance with `supplier_terms` kept as the queryable
   projection — not a reshape. **This decides the extraction schema, so it comes
   before extraction, not after.**
2. **Build extraction.** Schema per document type, prompt as a file in
   `api/prompts/` (ADR-0008 — never inline), raw output into `corpus/extracted/`
   and **never hand-edited** (rule 8), fixes into `corpus/corrections/` with a
   note per fix. This is the paid path, so it carries a call ceiling and a spend
   ceiling like every other runner (rule 2).
3. **Gold set — label all 40.** The *Open questions* estimate of "~40, never
   confirmed" is now confirmed at exactly 40, and the rule already written there
   says: under 40, label all of it and skip gold-set sampling. `PLAN.md` asks for
   30; the corpus is 40, so sampling would save little and cost a denominator.
4. **`TIMELINE.md`, the gap query, injection specimens, `KNOWN_ISSUES.md`,** and
   the README's four-number block. Note done-condition 6's own warning: for a
   corpus we generated, an empty `KNOWN_ISSUES.md` means the injected difficulty
   was too gentle, not that the pipeline is good.

**Two repo-level decisions are waiting and neither is mine to take:** a committed
`.gitattributes` (without it, every hash in this project is wrong on a Windows
clone), and where the two Windows-only ingest environment variables belong. Both
are described in *Last session*.

**Do not reopen the Phase 1 eval to chase the remaining items** — they are listed
under *Named debt* and each is cheap to do **inside** a later phase that touches
the prompt anyway. Reopening it on its own is what three sessions did, at ~$9.83
and diminishing returns. **And the rule that cost the most to learn: never
re-measure only the questions that failed.** It read 97.1% with zero
silent-wrongs against a clean 91.4% with five.

## Measured numbers

_SQL, current prompt `f3b7a9193a56f10d`, current 49 questions, **clean triple
(runs 3–5, 147 fresh responses, 2026-08-09)**:_ not-view-covered **91.4% (96/105,
CI 85–95%)**, overall 92.8% (128/138), view-covered 97.0% (32/33), **cross-run
variance 12.2%**, silent-wrong in 5 distinct questions (q011, q026, q034, q043,
q047) — **none of them stable; each is correct in at least one of the three runs.**
Execution errors in q026 and q050, both statement timeouts, both verified against
an idle database so the attribution is the model's idiom and not test-suite load.

**Quote this triple, not runs 0–2 of the same prompt.** Those read 97.1% and 0.0%
variance because only the three questions that had failed were re-measured after
being fixed — failures got a second draw and successes did not. The clean triple
over the identical set is 5.7 points lower, and the instability turned out to sit
in the questions that had *not* been re-rolled.

_SQL, previous prompt `415953964db74b80` (n=47, six runs, 282 responses):_
not-view-covered **91.9% (182/198)**, view-covered 98.5% (65/66), variance 10.6%
and 4.3% on its two independent triples, 12.8% pooled. **Do not quote the pooled
interval as if it were tight** — six runs of the same 47 questions are clustered,
so Wilson understates it.

_Attempts-to-correct:_ still not measured; no retry loop exists.

_Extraction:_ Phase 2, not started.
_Injection specimens:_ Phase 3, not started.

## Named debt carried forward

- **`corpus/parsed/` and `PARSE.csv` are committed but unchecksummed.**
  `CONVENTIONS.md` and ADR-0006 both say `verify-corpus` covers `parsed/` and
  `extracted/`; it counts PDFs plus the manifest and nothing else, so it passes
  41/41 while checking none of the parse output. `verify-parse` re-derives three
  of the 40 from source, which is a stronger check on those three and no check at
  all on the other 37. **Extend `CHECKSUMS.txt` when `extracted/` lands**, since
  that is the same gap one layer down and both close with one edit.
- **No `.gitattributes`.** With `core.autocrlf=true` — Git for Windows' default —
  every text file checks out CRLF and every byte-level hash in this project is
  wrong: the prompt freeze, the seed fingerprint, and `PARSE.csv`. Fixed by local
  config in one clone on 2026-08-11; **the repo still has no durable fix.**
- **`full×3` is done, but it is one sample of three runs.** Variance at 10.6%
  sits right on ADR-0001's line; another triple would move it either way.
- **q036's refusal is not reliable** — two of three. It is the behaviour the
  project's argument rests on.
- **No retry loop exists**, so ADR-0001 threshold 4 has never been measured.
- **On the live path, a scoped query's `WHERE` clause is the model's to write.**
  The scope reaches the prompt carrying the predicate itself
  (`store_id = 1 (Kothrud, Pune)`), and `check_scope` is a tripwire behind it —
  but that tripwire can only fire when `store_id` is among the result columns.
  Pattern-matching the generated SQL for the predicate was deliberately not
  done: that is instance eight's defect (regexes guessing at SQL structure). The
  real fix is a per-store database role, and it is not Phase 1. Demo mode is not
  affected — there the predicate is substituted, not requested.

## Vertex: verified working, one surprise


- Token mints from the service account; `gemini-3.6-flash` answers.
- **It serves from `location=global` ONLY** — 404 in us-central1 and
  asia-south1. Model string and serving location are independent variables and
  only the string was being pinned. `corpus/PIPELINE.json` now records both,
  and ADR-0006's claim is amended to "pinned model string AND serving
  location".
- For Phase 2, `location=global` needs a data-residency decision before real
  documents are sent.

**Still unverified: who pays.** The Cloud Billing API is not enabled on the
project, so credit coverage, balance and expiry cannot be read from here.
Calls succeed, which proves access and quota — not that credit is being drawn
rather than a card.

## Model providers and live limits


Decided 2026-08-06. Reasoning in **ADR-0009** — the split is on **data terms**,
not rate limits.

| Role | Provider | Tier | Model |
|---|---|---|---|
| `PLAN` | Gemini API | Free | Flash, pinned version string |
| `CLASSIFY` | Gemini API, or local Ollama if RAM allows | Free | Flash-Lite |
| `EXTRACT` | Vertex AI, service account | **Paid** | Phase 2 only |

**Mistral: fallback, documented, deliberately not wired.**

### Terms — verified 2026-08-06, re-check before Phase 2

- **Free tier trains on your data.** [ai.google.dev/gemini-api/terms](https://ai.google.dev/gemini-api/terms)
  (effective 2026-03-23, updated 2026-04-28): Google "uses the content you
  submit ... to provide, improve, and develop Google products and services",
  and "human reviewers may read, annotate, and process your API input and
  output." The page says outright: do not submit personal information to the
  unpaid services.
- **Paid tier does not.** Same page: Google "doesn't use your prompts ... or
  responses to improve our products".
- **Vertex** states customer data stays out of the foundation model training
  corpus — but ⚠️ **this was confirmed from Google Cloud documentation, not the
  canonical Service Specific Terms, which would not load.** Read those directly
  before the first extraction run over real documents. If they disagree,
  ADR-0009 is void.

### Rate limits — NOT YET VERIFIED, and only you can

Google's rate-limit page no longer publishes a table. It says limits "can be
viewed in Google AI Studio" and links
`https://aistudio.google.com/rate-limit?timeRange=last-28-days`. That view is
behind your login, so **these numbers have to come from you**, per project
behind the key.

Fill in before the first eval run — they set iteration speed and nothing else
should be guessed from blogs:

| Model | RPM | TPM | RPD |
|---|---|---|---|
| `gemini-3.6-flash` (PLAN) | __ | __ | __ |   <- CONFIRMED enabled and answering
| `gemini-3.5-flash-lite` (CLASSIFY) | __ | __ | __ |

⚠️ **Also confirm `gemini-3.6-flash` is free-tier eligible in YOUR project.**
It is two weeks old (GA 2026-07-21) and appearing on the public pricing page is
not the same as being enabled for a given project. If it is not, fall back to
`gemini-3.5-flash` and record the change.

Third-party figures circulating for the free tier — 10 RPM / 250 RPD for Flash,
15 RPM / 1000 RPD for Flash-Lite, 250k TPM — are **unverified blog numbers and
should not be relied on.** One of the same sources claimed Pro was removed from
the free tier in April 2026, which Google's own pricing page (updated
2026-08-05) contradicts: `gemini-2.5-pro` is listed as free-tier eligible. That
is the accuracy level of those tables.

**Free-tier eligible Flash models**, from the official pricing page
(2026-08-05): `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`,
`gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`. Pin one
exactly; never a floating alias.

**Budget:** a GCP budget alert must exist before the first Vertex call.

### Sampling parameters are gone

`temperature`, `top_p` and `top_k` are **deprecated and ignored** on both chosen
models, and return HTTP 400 on future generations (Gemini release notes,
2026-07-21). ADR-0006 is amended: extraction reproducibility is now **measured
empirically**, not asserted from a sampling parameter, and nothing in this
project should send those fields. Consequence for ADR-0001 threshold 3: it now
measures the model's inherent nondeterminism rather than prompt instability —
still the right thing to measure, but do not read it as a prompt-quality
metric.

## Locale — resolved, India


Currency INR, timezone Asia/Kolkata, modelled as a Maharashtra grocery chain
(Kothrud/Pune, Gangapur Road/Nashik, Dharampeth/Nagpur). This is now final and
the eval set can be written against it.

**Two things still to check against the corpus when it lands**, both flagged in
the LOCALE block of `api/scripts/seed.py`:

- **Festival dates.** Solar ones are fixed; the lunisolar and lunar ones —
  Diwali, Holi, Ganesh Chaturthi, and especially the two Eids — are marked
  `APPROX` in the code. Wrong festival dates are visible to any Indian reviewer.
- **GST slabs.** India simplified the slab structure during 2025, so the
  per-category rates are indicative. Real invoices in the corpus carry the real
  rates and those win.

Correcting either means editing that block, `make seed-generate` at both sizes,
and committing the regenerated `seed/small/` + `seed/CHECKSUMS.txt` — **which
invalidates every eval expected result set written before it.** Do it before
Phase 1's eval set if it is going to happen at all.

## Facts about the data someone will otherwise rediscover the hard way


- **`small` and `full` are independent datasets, not subset and superset.**
  Reference data (600 products, 18 categories, 12 suppliers) is identical;
  stores, history length and volume differ. **Every eval runs against `full`.**
  An eval written against `small` will not hold.
- **`make db` is the slow path (~60s at full); `make reset` is the fast one
  (~2–6s).** `make db` builds `pos_template` and marks it a template; `reset`
  clones it, which is a file copy. This is also the ADR-0005 test-isolation
  mechanism, and it answers ADR-0004's worry about `agent_runs` churn in Phase 4
  forcing a full rebuild each time.
- **Seed generation runs in a digest-pinned `python:3.12-slim`**, in both the
  Make target and CI. Bare Python is not enough: libm differences can flip a
  Poisson draw and the tzdata version moves timestamps. The claim is
  byte-identical *in the pinned image*, asserted in CI at both sizes.
- **`sale_lines.quantity` is signed** — negative on returns — so `SUM(quantity)`
  is net, not gross. `daily_product_sales` names `units_sold`, `return_units`
  and `net_units` separately. Good eval question; likely silent-wrong trap.
- **The festive season is the strongest signal in the data.** Navratri →
  Dussehra → Dhanteras → Diwali is one continuous six-week build, not four
  spikes: ₹417k/day against a ₹267k/day baseline, peaking at 2.75x on 17 Oct
  2025 (the day before Dhanteras) and collapsing to a 12-day slump afterwards.
  Festivals are their own factor (`Festival` + `build_day_factors`), separate
  from the category sinusoid, because a sinusoid is symmetric and slow and this
  shape is neither. Overlapping festivals combine by **max, not product** —
  multiplying four ramps produces a number no shop has seen.
- **`full` contains exactly one Diwali (Oct 2025); `small` contains none**, since
  `small` starts 2026-01-02 and Diwali 2026 is past `DATA_END_DATE`. Do not
  write a Diwali eval question and test it on `small`.
- **Ganesh Chaturthi and Gudi Padwa are weighted per store** — Pune indexes
  above Nagpur. Everything else applies chain-wide.
- **GST is per category AND per date.** The 22 September 2025 reform is inside
  the window: slabs went 0/5/12/18/28 → 0/5/18/40, aerated drinks 28→40,
  dairy/snacks/ready-to-cook/personal care/health/baby/pooja 12→5. Rates live
  in `gst_rates` with the same `valid_period @> date` pattern as
  `supplier_terms`. Effective rate measured at 8.42% before and 6.68% after;
  the naive blend across the boundary is 7.52%, **true of no period**.
  `sales.subtotal` is net of tax and `total = subtotal + tax_total`; "revenue"
  normally means `subtotal`.
- **Regional festival weighting exists but is NOT measurable at store level.**
  Ganesh Chaturthi and Gudi Padwa are weighted per store (Pune 1.00, Nashik
  0.88, Nagpur 0.72), but the `max` combination with unweighted national
  festivals in the same window dilutes it below Poisson noise. An eval question
  about it had an expected answer that contradicted its own premise, and was
  replaced (q027 is now about store size confounding a comparison, which the
  data does support). **Do not write an eval question about regional festival
  differences** without first widening the spread and re-measuring.
- **Prices are category-banded, not free log-normal** (`CATEGORY_PRICE_MEDIAN`
  × `variant_price_factor`). Without that the generator produced ₹225 bananas
  beside a ₹78 five-litre oil jar — which loads cleanly, passes every
  constraint, and makes any revenue question answer noise.
- **Velocity divides by days the product was *available*,** not by 30.
  `stockout_days` exists because sales are capped by stock, so the products a
  restock question is about are exactly the ones whose sales understate demand.
- **`seed/full/` is gitignored** (63MB). `seed/small/` is committed (5.5MB), and
  `seed/CHECKSUMS.txt` covers both, so the byte-identity claim is verifiable for
  `full` without shipping it.
- 21 of 600 products end at zero stock and ~150 sit below reorder point. That is
  realistic, not a defect — but it means the beat-1 query wants
  `AND on_hand > 0` to ask "about to run out" rather than "already out", and a
  `units_per_day DESC` tiebreak so the ordering is total.

## Open questions — ask me, don't decide


These are unresolved by design. If you hit one, stop.

- **Amendments vs. supersessions. Now decidable — nothing is waiting on data.**
  Phase 0's `supplier_terms` is a wide table that supersedes as a set, which is
  right for supersessions and right for text-to-SQL. The corpus contains **2
  clause-level amendments**, generated deliberately so the pipeline meets the
  harder case rather than the one we would have picked. If they are to be
  modelled as amendments, the answer is a narrow `supplier_term_clauses` table
  for clause-level provenance with `supplier_terms` kept as the queryable
  projection — not a reshape. **Decide before the extraction schema is written.**
- **Available RAM** — now only for the `CLASSIFY` Ollama fallback and Phase 3's
  local embeddings, since ADR-0010 routes `PLAN`, `CLASSIFY` and `EXTRACT` through
  Vertex. Embeddings stay local at every tier and need little.
- **Data residency.** Vertex serves `gemini-3.6-flash` from `location=global`
  **only** — 404 in us-central1 and asia-south1, measured. The first extraction run
  therefore sends real document content to an unpinned region. **Needs answering
  before any document is sent, not after.**
- **The canonical Vertex terms.** ADR-0009 rests on "customer data stays out of the
  foundation model training corpus", confirmed from Google Cloud documentation
  rather than the terms themselves. If they disagree, ADR-0009 is void. Read them
  before the first extraction run.
  **Retried 2026-08-09 and narrowed, not resolved:** `cloud.google.com/terms/service-terms`
  *does* load now — the earlier "would not load" is stale — but the fetched text
  carries no Vertex or generative-AI clause at all, only data location (§1) and
  Pre-GA terms (§5). The data-governance page has moved to
  `docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance` and returns
  only its navigation shell to a fetcher, because the body is client-rendered. **So
  it needs a browser, not a tool** — and the specific thing to look for is the
  "Zero Data Retention" section that page's title advertises.
- **Whether the corpus covers perishables.** If yes, the dynamic pricing cut flips
  and it belongs in Phase 6.
- **The approval-card wireframe** (Phase 4). Palette and type are settled — proposed
  in `docs/DESIGN-TOKENS.md` and built from; say if they should change and it is a
  `tailwind.config.ts` edit.

**Resolved since this list was written — removed, not forgotten:** the
text-to-SQL outcome (ADR-0001, resolved; Phase 1 closed), role-scoping (decided,
and `sql_generate.md § Access scope` is filled in), the `PLAN` provider (ADR-0010
routes everything through Vertex), the palette and type pairing, and **corpus
size — it is exactly 40, so the rule that was written against the estimate now
applies: label all of it and skip gold-set sampling.**

**Resolved — don't re-ask:** hours (session-based, see `PLAN.md`), document
clearance (personal, publishable; PII scan still required in Phase 2), frontend
(Next.js + Tailwind, ADR-0007).

## Decisions made mid-build


Anything decided in a session that isn't yet an ADR. Promote or delete.

- **`effective_from`/`effective_to` landed in 001, not Phase 2.** Adding them
  later would have meant a backfill plus rewriting every Phase 1 query that read
  `suppliers.payment_terms_days`. A generated `valid_period daterange` column
  carries half-open `[from, to)` semantics natively, so a query says
  `valid_period @> DATE '...'` and cannot get the boundary wrong. A gist
  exclusion constraint forbids overlap and permits gaps — gaps are how "no terms
  in force" stays distinguishable from "supplier not found". Verified against
  PG16 before the migration was written.
- **`sale_operators` is a separate table with no grant to `pos_readonly`.** ADR-0002
  says the agent reports patterns, never people; this makes the query interface
  structurally incapable of returning who rang up a sale, rather than trusting a
  prompt. Staff display names are `Clerk 03`-style labels, never person-like.
  Candidate for promoting into ADR-0002 as an implementation note.
- **`schema.md` is generated from `COMMENT ON` statements** by `make schema-doc`,
  and CI fails if the committed copy is stale. `business_context.md` stays
  hand-written. Candidate for an ADR if it survives Phase 1.
- **`store_id` and `business_date` are denormalised onto `sale_lines`** and held
  true by a three-column composite foreign key, so velocity queries never join
  the header and the copies cannot drift.
