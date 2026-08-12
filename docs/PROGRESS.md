# Progress

**Read this first. Write it last.** This is the only memory across sessions.

Keep it short. Delete resolved items rather than accumulating history — git has
the history. This file answers one question: what does the next session need?

---

## Current phase

**Phase 2 — Corpus ingestion. IN PROGRESS. The corpus exists and is parsed;
extraction is built and has never been run, and that run is the gate.**

Phase 1 closed 2026-08-09 and the reasoning for closing it is kept below, because
it is what the eval numbers in the README rest on.

**Where Phase 2 stands against `PLAN.md`'s seven done-conditions: four hold.**
1 (reproducible parse asserted in CI), 4 (`TIMELINE.md` hand-verified **and** a
date inside a real gap returns nothing in force), 6 (`KNOWN_ISSUES.md` non-empty),
7 (PII scan recorded honestly as vacuous). Three do not: no extraction, no gold
set, no injection specimen, and the README's four-number block is blank.

**Condition 4 was closed on 2026-08-11 by regenerating the seed.** The corpus had
no coverage gaps at all — every predecessor ended the day its successor began —
while `corpus/README.md` asserted it did. `LAPSED_SUPPLIERS` in `seed.py` now
lapses SUP-06 for 48 days and SUP-11 for 78, drawn from their own RNG substream so
one field in one row per supplier moved and nothing else in the seed did.

- **Corpus: done.** 40 synthetic documents generated from the seeded database —
  24 contracts (including 2 clause-level amendments), 10 invoices, 3 catalogs,
  3 policies. 10 carry an injected difficulty, each re-derived from the rendered
  PDF before the manifest is written. Byte-identical on regeneration.
- **Parse: done, and now actually checked.** All 40 parsed with Docling into
  `corpus/parsed/` with `PARSE.csv`. `verify-parse` re-parses a **4-document**
  sample and asserts byte-identity in CI — see *Last session*, because until
  2026-08-11 it was a stub that could only fail, and the sample was three
  documents that could not fail either.
- **Extraction: built, and never run.** `api/prompts/extract.md`,
  `pos_copilot.extract`, `scripts/corpus_extract.py`, `make extract` /
  `make extract-stub`. Every path is exercised against a stub — no key, no
  network, no quota — and **no model has been called.** `corpus/extracted/` does
  not exist yet, so nothing here is a measurement.

**Amendments vs. supersessions is decided: clause-level provenance.** Extraction
records what a document *says*, never what was in force — the amendment that
varies three clauses yields three clauses, and the set in force is computed later
from the whole chain. The alternative makes the model perform the inheritance, and
then a correct inheritance and an invented value are indistinguishable in the
output, which is the failure this step is measured on. **No migration was
written**: `supplier_term_clauses` would regenerate `schema.md`, change the SQL
prompt fingerprint and void 147 cached responses for ~$3.30, and no Phase 2
done-condition needs a table. It belongs in Phase 3, where retrieval queries it.

**Nothing gates the first paid run any more. All three closed 2026-08-12.**
**Budget alert: created**, $15/month, thresholds 50/90/100% actual plus 100%
forecasted (reported by the project owner — the Cloud Billing API is still not
enabled, so nothing here can read the console). **Data residency:** accepted with a
tripwire. **Canonical Vertex terms:** accepted for a synthetic corpus, with the same
tripwire — a no-training clause protects confidential content and there is none
here, so reading the terms is owed before a *real* document is sent, not before 40
generated ones. Both write-ups are in ADR-0009.

**What that ADR now concedes, and it should not be lost:** its free-tier/paid split
was justified on data terms, and for a synthetic corpus that justification is thin.
`EXTRACT` is on Vertex for rate limits and a service-account credential, not for
data protection. **The run is unblocked; the reasoning behind the ADR is weaker
than it reads.**

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
| 2 Corpus ingestion | **in progress** | Corpus generated (40 documents) and parsed; both reproducible and asserted. **4 of 7 done-conditions hold.** Extraction is built and unrun, and it is the gate. **Nothing blocks the first paid run — all three gates closed 2026-08-12** (budget alert created; residency and the Vertex terms both accepted with a synthetic-corpus tripwire, ADR-0009). What is missing is a service-account credential, which is not a decision |
| 3 Document Q&A | not started | |
| 4 Procurement agent | not started | |
| 5 Polish | not started | |

## Last session

_Date:_ 2026-08-12
_What landed:_ **The Phase 2 branch reached `master`, and the state document that
described Phase 2 turned out to be two commits behind it.** No model calls, no
spend, no code and no artifacts changed.

### The branch was merged, and the repo is one branch again

`phase-2-corpus-docs` was 9 commits ahead of `master` and 0 behind, so the merge
was a fast-forward: `c7e9ef6..48151b3`, 36 files, +3041/−288. Pushed. Then both
merged branches were deleted local and remote — `phase-2-corpus-docs` and the
`codespace-…` branch already absorbed by PR #1 — and the remotes pruned. **The
repo is now a single branch**, `master`, local and remote in sync.

### `PROGRESS.md` was describing a phase two commits behind the one in the repo

Ten claims here and one heading in `KNOWN_ISSUES.md` contradicted either the repo
or this file's own other paragraphs. The cause is in the history: **48151b3 changed
the artifacts and `KNOWN_ISSUES.md` and did not touch `PROGRESS.md`**, so the file
kept describing the state before its own session's last three commits. Reconciled
in `72f65ce`; the individual corrections are in that commit's message and in the
sections above, corrected in place.

Worth naming, because it is this project's recurring class and this is the fourth
instance of it in two sessions: **the previous session's own entry says all four
state documents had gone stale and that `HANDOFF.md` exists precisely so that can
be corrected.** It then went stale again, in the same session, by the commits that
closed the session. Being the file that warns about staleness confers nothing.

The one that would have cost the most: **"`verify-parse` passes" was listed as
evidence the system was green**, after that check had been deliberately rewritten
to fail outside the reference environment. Read as a formality, it invites the next
reader to treat a correct failure as a broken repo.

### `make` does not run on this machine, and nothing said so

macOS 25.5, and every Make target dies before its first line with *"You have not
agreed to the Xcode license agreements."* `sudo xcodebuild -license` is owed before
`make` is usable here. The underlying scripts run fine directly through `uv`, which
is how everything below was verified.

**Consequence for the parse layer: this is a third platform** — after the Linux
codespace and the Windows checkout — **and it has not been measured.** `make ingest`
and `make verify-parse` have never run here, so whether macOS reproduces the
reference parse is unknown, not assumed either way. Entry 2 of `KNOWN_ISSUES.md`
applies: run `verify-parse` before trusting any parse produced on this machine.

_What didn't:_ **the extraction run — but two of its three gates closed, and only
the Vertex terms are left.** **Data residency:** accepted with a tripwire
(ADR-0009). **Budget alert: decided at $15/month and created**, with the rule now
in `PLAN.md` → *Money*, which is where `PROGRESS` had been citing it from all along
without it being there. **The canonical Vertex terms closed too**, accepted for a
synthetic corpus with the same tripwire — so **all three gates are down and the run
is unblocked.** Three further open questions closed alongside: available RAM
(8 GB), the Windows env-var placement, and perishables.

**`verify-parse` was run on this Mac and read 2/4** — see below; it is not on the
critical path and nothing was changed in response to it.

**Phase 2 stays at 4 of 7** — decisions are not done-conditions, and nothing here
was measured.
_Anything half-finished someone would trip over:_ No. Documentation only, committed
and pushed.
_Is the system in a working state?_ **Yes, with the verification stated exactly.**
What ran here: the 24 corpus tests (`test_corpus_timeline`, `test_corpus_checksums`)
pass, `corpus_checksums --check` reports 82 artifacts matching with none unlisted,
and `git add --renormalize` produces no byte changes. **What did not run here, and
is therefore carried forward from 2026-08-11 rather than re-confirmed:** the full
suite, ruff, `web-check`, and `verify-parse` — the first three because `make` is
blocked, the last because this is not the reference environment. Neither edited file
is checksummed or asserted against, so nothing downstream of them could have moved.

## Session before this one — 2026-08-11

**Kept rather than pruned**, against this file's own "delete resolved items" rule,
because its findings are load-bearing: the parse platform split, four checks that
could not fail, and the newline defect's third and fourth instances. Prune it once
extraction has run and Phase 2 closes.

_What landed:_ The environment stood up on Windows, and **four checks that were
not running turned out to be wearing the label of checks that were.** No model
calls, no spend.

### The database exists, on Neon, and done-condition 4 is closed

**Tooling, none of it needing admin:** psql 18.4 (EDB binaries zip, client files
only, extracted to `%LOCALAPPDATA%\pgclient` — the winget installer wanted UAC and
the full archive breaks Windows' 260-char path limit on bundled pgAdmin), and GNU
Make 4.4.1 via `ezwinports.make`. Local Python reproduces the pinned seed
byte-identically, so **Docker is not needed on this machine.**

**The PG16 assumption held.** All three migrations applied cleanly on
**PostgreSQL 18.4** — `btree_gist`, the generated `daterange` columns and both
gist exclusion constraints. `PROGRESS` recorded that design as "verified against
PG16"; it survives two major versions.

**Done-condition 4 is closed**, and the route there is the finding:

1. The seed was regenerated with `LAPSED_SUPPLIERS`. First attempt used SUP-03
   and SUP-07; `make eval-expectations` **refused to write** because q014 asks for
   Nilgiri Beverage Company's terms in March 2025 and SUP-07's lapse covered that
   date, so its reference query correctly returned nothing. An empty expectation
   scores every wrong answer as correct. SUP-06 and SUP-11 are the only two
   suppliers no eval question names — established mechanically.
2. **2 of 49 expectations moved**: q017 and q048, only in the rows for the two
   lapsed suppliers. Ten other suppliers byte-identical in q048.
3. `make corpus` changed **exactly 2 of 40 PDFs**.
4. The `is_active` gate was re-checked as `HANDOFF.md` requires: 600/600 products
   still active, and the edit touched only `supplier_terms`.

**Neon's free tier cannot run this project's database design at `full`** — 512 MB
cap against a 263 MB database, so the template-plus-clone `make reset` and
ADR-0005 both need does not fit. See *Named debt*.

### The Docling parse is platform-dependent, and I said otherwise

Re-parsing the whole corpus on Windows against the Linux-generated committed
output: **5 of the 40 documents parse differently.** Four are
heading-versus-paragraph flips. The fifth, `invoice-sup-12-5436` — the
`table-spans-page-break` document — **lost its table entirely**, parsing to
the bare word `Supplier`. Re-parsing twice on Windows gives identical output, so
it is a platform split, not randomness.

**The count first published here was 4 of 38 and it undercounted**: the two
documents whose PDFs had just been regenerated were excluded, because there was
nothing to compare them against. Parsing their *previous* PDFs and diffing against
the committed output put `contract-sup-11-20230907` in the divergent set too. **A
sample that silently excludes the cases you changed is not measuring the
population you think it is.**

**I claimed the opposite earlier in this session**, from one document and then
from `verify-parse`'s 3/3. Those three happen to be platform-stable; 5 of 40 are
not. That is `verify-parse`'s sample hiding the property it names — the
recurring class, in a check written the same day, by me. **Fixed by widening the
sample to include a document that diverges**, so it is now 3/4 on Windows.

**ADR-0006's "deterministic parse layer" should be scoped to "within a pinned
environment".** The seed layer already runs in a digest-pinned image for exactly
this reason; the parse layer pins Docling's version but not its environment. CI
runs one platform, so this is not assertable there at all.

The Windows parse was **discarded rather than committed**, so `corpus/parsed/`
keeps the table — with two deliberate exceptions, since
`contract-sup-06-20240928` and `contract-sup-11-20230907` were holding the parse
of their *previous* PDFs. **That was not cosmetic:** until it was fixed the lapse
existed in the database, the manifest and the PDF but not in the layer extraction
reads and Phase 3 will embed, so a document-grounded question would still have
answered that coverage was continuous — the exact thing done-condition 4 exists to
disprove. **Both were re-parsed**, with the platform cost measured first: SUP-06
reproduced the committed output byte for byte, SUP-11 loses one `##` heading marker
on line 3, which a `make ingest` in the reference environment restores. Recorded in
`corpus/KNOWN_ISSUES.md` entry 2, which carries the commands.

### Two more instances of the newline defect, and two probes of mine that could not fail

`seed.py` and `eval_expectations.py` both wrote artifacts without `newline="\n"` —
**instances three and four.** The `seed.py` one is the worst-placed in the
project: that file's bytes *are* the seed fingerprint, so with `.gitattributes`
normalising to LF on commit it would have written a fingerprint not matching the
file it committed, surfacing on someone else's clone as "49 expectations computed
against a different seed".

And twice the broken thing was my own verification: a diff keyed on
`expected_rows` when the field is `expected` (reporting a confident "0 of 49
changed"), and a grep over `evals/.cache/`, which does not exist here at all.
**Both returned clean results while checking nothing.**

`corpus/README.md` also published `scanned-200dpi-skewed | 4` when the manifest
has always had 5 — checked against HEAD, so it shipped wrong rather than drifted.
Now asserted against the manifest.

### The parse layer was never actually verified

- **`verify-parse` was a stub that could only fail.** It skipped while
  `corpus/parsed/` was absent and printed `not implemented; exit 1` once it was
  not — so **CI has been red on master since the parse landed**, on the last step
  of the run. It now does what ADR-0006 specifies: re-parses a committed sample
  and asserts byte-identity, with a counter so it cannot confuse "found no
  differences" with "compared nothing". The sample was three documents when this
  was written and is **four** now — the fourth was added later the same day, once
  the three turned out to share the property that made the check useless.
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

### Three documents parse identically on Linux and Windows, and only those three

The 3-document `verify-parse` sample re-parsed on **Windows** is byte-identical to
output generated in a **Linux** codespace, OCR included, on a 200dpi skewed scan
with no text layer. The OCR path surviving a platform change is a real result. It
is also the whole of the result.

**This was written up as "the parse is deterministic across platforms — measured,
not assumed", and the same session disproved it:** the whole-corpus comparison
above puts 5 of 40 documents in the divergent set. These three are stable because
they are the sample, and the sample was fixed before the property was ever
measured — which is exactly why `invoice-sup-12-5436` was added to it afterwards.
**Read this as evidence about three documents, never about the corpus**, and note
that the overclaiming heading outlived the measurement that retracted it by a day.

### Extraction, built against a stub, never once called a model

`api/prompts/extract.md` (one prompt, `{json_schema}` injected per document type,
document text below every instruction in a delimited block per rule 6),
`pos_copilot.extract` (schemas, structural validator, invoice reconciliation),
`scripts/corpus_extract.py` (cache, 60-call and $2.00 ceilings, canonical-run
guard), 31 stub-driven tests.

**Two defects found by probing it, neither by reading it:**

- **The stub could write invented values into `corpus/extracted/`.** The report
  guard covered `EXTRACT.csv` but the per-document writes were unconditional, so
  a plumbing run would have left 40 files nothing downstream could distinguish
  from real extractions. Refused up front now.
- **The test for that guard could not fail.** It passed `--out tmp_path`, so the
  out-of-place check was what made it green and the stub check never executed.
  Rewritten to aim at the canonical directory, then validated by disabling the
  guard and watching it fire — which is how the 40 files were seen. **A probe
  that passes for the wrong reason is instance twelve**, and it was written *in
  this session*, by someone who had spent the morning fixing four others.

`MODEL_EXTRACT` was also missing from the Makefile's `export` line — the
`-include .env` defect already written down two sections above this one.

### The corpus has no coverage gaps, and three documents said it did

Measured from `MANIFEST.csv`: **12 suppliers, 24 contracts, two each, and every
predecessor ends on the exact day its successor begins.** Zero gaps. The only
dates with nothing in force are before each supplier's first contract, earliest
2023-09-07 — a much weaker case, because "before any contract existed" is hard to
tell apart from "not found", which is the distinction demo beat 2 exists to show.

**`PLAN.md`'s done-condition 4 therefore cannot be satisfied by this corpus.**
`corpus/README.md` asserted the opposite — *"a date with no contract in force is a
real gap in the corpus rather than a staged one"* — which described what
`valid_period` permits rather than what the generator produced. Same shape as the
`expected_on` schema comment and the `business_date`/`sold_at` claim: **a document
asserting a property the artifact does not have.** Corrected in place, so the
correction is visible rather than tidy.

**Fixing it means regenerating with a deliberate lapse for one or two suppliers,
and that must happen before extraction is paid for** — regenerating changes the
documents, changes the parse, and voids extracted output. It is now an open
question below. It also needs Postgres, so it is blocked on Docker locally.

`corpus/TIMELINE.md` and `corpus/KNOWN_ISSUES.md` now exist and both say this
plainly. `test_corpus_timeline.py` asserts the claim is still true, so the day a
regeneration introduces a gap, the three documents describing its absence fail
together instead of ageing quietly.

### `verify-corpus` was checking none of the parse output

It listed the 40 source PDFs plus `MANIFEST.csv` and checked completeness by
counting PDFs — so it reported **41/41 while verifying none of the 40 committed
parse artifacts**, which `CONVENTIONS.md` and ADR-0006 both say it covers. Now 82
artifacts, and the completeness half is a set comparison rather than a count:
`sha256sum -c` verifies the paths a file mentions and is structurally blind to the
ones it omits, which is precisely how the gap survived.

### Two things a fresh clone trips over, neither of them in the repo

- **`core.autocrlf=true` and no `.gitattributes` broke every hash in the
  project.** On Windows this failed two tests with confidently wrong messages —
  "prompt changed since the freeze" and "49 expectations computed against a
  different seed". Neither was true: LF-normalising the bytes reproduces
  `PROMPT_FREEZE.json` and the seed fingerprint exactly. **Fixed:
  `.gitattributes` is committed.**

  The naive version of that file would have broken CI, which is the part worth
  keeping. Python's `csv` module defaults to `lineterminator="\r\n"`, nothing in
  the corpus scripts overrides it, so `MANIFEST.csv` and `PARSE.csv` are committed
  with CRLF and `CHECKSUMS.txt` records the CRLF hash — `* text=auto eol=lf` alone
  would normalise them and fail `verify-corpus`, the exact check the file exists
  to protect. `*.csv -text` holds them as committed. **Caught by running
  `git add --renormalize .` before committing**, which is named in the file so the
  next edit runs it. `seed/*.csv` are LF because `seed.py` sets the terminator
  explicitly; the two conventions disagree and reconciling them rewrites
  `CHECKSUMS.txt`, so it is a deliberate regeneration rather than a cleanup.
- **`make ingest` needs two environment variables on Windows** and nothing says
  so: `HF_HUB_DISABLE_SYMLINKS=1` (hf_hub symlinks need admin or Developer Mode)
  and `TORCHDYNAMO_DISABLE=1` (TorchInductor shells out to MSVC `cl.exe`). Both
  are no-ops on Linux and in CI. **Decided 2026-08-12: `.env.example`**, commented
  out under a `Windows only` heading that names the confusing failure each one
  prevents — an hf_hub permissions error, and a missing-MSVC error naming nothing
  in this project.

### The state documents had gone stale, which is the defect this project names

`CLAUDE.md`, `README.md`, `PROGRESS.md` and `HANDOFF.md` all still said the corpus
did not exist, **two commits after it was generated and parsed.** `HANDOFF.md`
exists in the repo precisely so a stale state document can be corrected — and it
is the one pasted into a new session first. Being version-controlled made it
correctable; it did not make it correct. All four are reconciled in this session.

_The 2026-08-09 eval findings — six samples, threshold 3 retired, q017 and q036
fixed, q049 withdrawn — are preserved in `docs/HANDOFF.md` and in **Measured
numbers** below. They have not changed._

_What didn't:_ **the extraction run itself** — built and unrun, blocked on the
three gates open at the time; two of them closed on 2026-08-12, so *Next session
should* now lists one. Building the pipeline moved no
done-condition, and saying otherwise would count code as measurement. Phase 2 is
at 4 of 7, and all four are documentation and checks, not extraction.
_Anything half-finished someone would trip over:_ No. `make extract` refuses
without `MODEL_EXTRACT`; `make extract-stub` needs nothing and cannot write into
the committed corpus.
_Is the system in a working state?_ Yes. 259 passed, 33 skipped without a
database; ruff clean; `make web-check` clean; `verify-corpus` (82 artifacts)
passes; `git add --renormalize .` stages nothing.

**`verify-parse` is now an environment gate, not a formality, and is expected to
fail outside the reference environment.** Its sample was widened to include
`invoice-sup-12-5436`, the document that does diverge, so it reads `3/4 matched`
on Windows by design — a sample that cannot fail is not a sample. Passing it is
what separates "this machine reproduces the reference parse" from "this machine
produced something plausible". **Run it before trusting any `make ingest`
output**, and do not read a failure on a new machine as the repo being broken.


## Next session should

**Phase 1 is closed. Do not reopen the eval to chase the remaining items** — they
are listed under *Named debt* and each is cheap to do **inside** a later phase that
touches the prompt anyway. Reopening it on its own is what the last three sessions
did, at ~$9.83 and diminishing returns.

**Extraction is built and has never been run. Nothing gates it any more — all
three gates closed 2026-08-12. Run it.** In order, and the first step is not
optional:

1. **`make extract EXTRACT_ARGS="--limit 5"`, then read all five by hand** before
   the full 40. The stage-1 rule was written for evals and the reason carries
   exactly: a schema cannot be validated by inspection, only by use. The first
   staged run of the SQL set scored 0/4 and none of it was the model.
2. **The full 40** — ~$0.80 under a 60-call / $2.00 ceiling. Raw output into
   `corpus/extracted/`, **never hand-edited** (rule 8); fixes into
   `corpus/corrections/` with a note per fix.
3. **Gold set — label all 40**, then conditions 2, 3 and 5.

**Credentials are the only thing standing in the way**, and they are not a
decision: a Vertex service-account JSON, with `GOOGLE_APPLICATION_CREDENTIALS`
pointing at it in `.env`. That variable was missing from `.env.example` until
2026-08-12 — the one variable the paid path needs was the one variable nothing
documented.

Then, in order:

1. **Run `make extract --limit 5` and read all five by hand** before the full 40.
   The stage-1 rule is written for evals and the reason generalises exactly: a
   schema cannot be validated by inspection, only by use. The first staged run of
   the SQL set scored 0/4 and none of it was the model.
2. **Then the full 40** — ~$0.80 under a 60-call, $2.00 ceiling. Raw output into
   `corpus/extracted/`, **never hand-edited** (rule 8); fixes into
   `corpus/corrections/` with a note per fix saying what the pipeline got wrong.
3. **Gold set — label all 40.** The *Open questions* estimate of "~40, never
   confirmed" is now confirmed at exactly 40, and the rule already written there
   says: under 40, label all of it and skip gold-set sampling. `PLAN.md` asks for
   30; the corpus is 40, so sampling would save little and cost a denominator.
4. **`TIMELINE.md`, the gap query, injection specimens, `KNOWN_ISSUES.md`,** and
   the README's four-number block. Note done-condition 6's own warning: for a
   corpus we generated, an empty `KNOWN_ISSUES.md` means the injected difficulty
   was too gentle, not that the pipeline is good.

**Both repo-level decisions are now taken.** `.gitattributes` is committed, and
the two Windows-only ingest environment variables live in **`.env.example`**,
commented out under a `Windows only` heading with the failure each one prevents —
chosen because it is the file a fresh clone already copies and the Makefile
already does `-include .env`, so it needs no new machinery. Both are no-ops on
Linux, macOS and CI.

**Do not reopen the Phase 1 eval to chase the remaining items** — they are listed
under *Named debt* and each is cheap to do **inside** a later phase that touches
the prompt anyway. Reopening it on its own is what three sessions did, at ~$9.83
and diminishing returns. **And the rule that cost the most to learn: never
re-measure only the questions that failed.** It read 97.1% with zero
silent-wrongs against a clean 91.4% with five.

## Measured numbers

> ### ⚠️ STALE as of 2026-08-11 — the seed moved underneath them
>
> Every figure below was measured against seed fingerprint `206fb7a8e55164f9`.
> The seed is now **`e1ca4fb60f9e710e`** (the SUP-06 and SUP-11 lapses), and
> **two expected result sets changed**: q017 and q048, both of which read
> `supplier_terms` by period, and only in the rows for those two suppliers.
>
> **Re-scoring is not free here, contrary to the standing note below.** That note
> assumes `evals/.cache/` is present; it is gitignored and exists only on the
> machine that ran the original measurement. On this one it does not exist, so
> restoring these numbers means **re-running** — 147 calls, ~$3.30, and a Vertex
> service account. `CONVENTIONS.md` allows exactly two responses to this: re-run,
> or mark stale. This is the mark.
>
> The likely size of the error is small and bounded — two questions, one changed
> value each — but "likely small" is not a measurement, and the README quotes
> these figures as if they were.

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

_Extraction:_ Phase 2 — pipeline built, **never run**. No model has been called,
`corpus/extracted/` does not exist, so there is no number here to quote.
_Injection specimens:_ **Phase 2**, not started — `PLAN.md` done-condition 5 wants
at least one specimen with a committed trace showing the naive implementation
following it. Phase 3 gets injection *defence*; the specimens are what it is
measured against, so they are built first.

## Named debt carried forward

- **The eval response cache is not on this machine, and is not portable.**
  `evals/.cache/` is gitignored, so the 147 responses behind the published
  accuracy numbers exist only where they were generated. "Re-scoring is free" is
  true only there. Anywhere else, re-scoring means re-running: 147 calls, ~$3.30.
  Any future seed or prompt change should assume that cost rather than the free one.
- **A hosted Postgres cannot run this project's database design at `full`.**
  Neon's free tier caps a project at 512 MB; the seeded database is 263 MB, so
  the template-plus-clone that `make reset` and ADR-0005's test isolation both
  depend on does not fit. `make db` therefore fails at its final step, and the
  33 DB-marked tests cannot run at `full` there. Worked around by renaming the
  seeded template into place. `small` would fit; evals may not use it.
- **`make corpus` leaves `CHECKSUMS.txt` stale until `make ingest` runs.**
  Generation writes the sources-and-manifest listing; `corpus_ingest` refreshes
  the whole thing on a canonical run, because it is the last stage that writes
  artifacts. Regenerating documents always requires re-parsing them, so the two
  always run together — but `make corpus` on its own now fails `verify-corpus`,
  loudly and correctly. `make corpus-checksums` is the manual refresh.
- **The corpus and seed CSVs disagree about line endings.** `MANIFEST.csv` and
  `PARSE.csv` are CRLF because Python's `csv` default is RFC 4180 and nothing
  overrides it; `seed/*.csv` are LF because `seed.py` does. `.gitattributes`
  holds both as committed with `*.csv -text`, so nothing is broken — but two
  conventions in one repo is a trap for whoever next writes a CSV. Reconciling
  rewrites `MANIFEST.csv` and therefore `CHECKSUMS.txt`, so it rides along with
  the next deliberate corpus regeneration or not at all.
- **`full×3` is done, but it is one sample of three runs.** Variance at 10.6%
  sits right on ADR-0001's line; another triple would move it either way.
- ~~**q036's refusal is not reliable** — two of three.~~ **Retired 2026-08-12,
  against the committed results rather than by assertion.** `q036_causation_trap`
  is `correct ×3` in *both* triples of the current prompt
  (`evals/results/2026-08-09-sql.json` and `…-runs3-5.json`) — **6/6** — and 5 of 6
  on the previous prompt, its one `should_have_refused` at run index 1. The "two of
  three" was the pre-fix figure and had been carried as current debt ever since,
  while `HANDOFF.md` recorded 6/6 twenty lines from the same claim. It is still the
  behaviour the project's argument rests on, so re-check it whenever the prompt or
  `business_context.md` moves.
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

**Budget: $15/month, decided and created 2026-08-12** — thresholds 50% / 90% /
100% actual plus 100% forecasted, scoped to this project only. Reasoning, spend to
date and per-phase estimates in `PLAN.md` → *Money*. **This gate is closed.**
Reported by the project owner; the Cloud Billing API is still not enabled, so it
cannot be verified from inside the repo — which is also why *who pays* remains
unanswered below.

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
- ~~**Available RAM**~~ **— answered 2026-08-12: 8 GB.** Consequences, both small:
  a local Ollama fallback for `CLASSIFY` is **not viable** (a quantised 7B is
  ~4–5 GB, leaving nothing for Postgres and the app), but ADR-0010 already routes
  `CLASSIFY` through Vertex so nothing depends on it. Phase 3's embeddings are
  `bge-small-en-v1.5` at ~130 MB and are comfortable. **Docling is the one tight
  spot:** ~2–4 GB peak with layout, tableformer and OCR loaded, plus a 3–5 GB
  install (torch, docling, onnxruntime, rapidocr) that this machine has never
  done — which is one reason parsing stays in the reference environment.
- ~~**Data residency.**~~ **Decided 2026-08-12: accepted, with a tripwire.**
  Vertex serves `gemini-3.6-flash` from `location=global` **only** — 404 in
  us-central1 and asia-south1, measured — so extraction sends document content to
  an unpinned region and no configuration avoids it. Accepted **because the corpus
  is synthetic**: there is no confidentiality interest for a residency guarantee to
  protect. **The tripwire:** any document not generated by this repo landing in
  `corpus/sources/` voids the decision and it must be retaken. Written up in
  ADR-0009. **This does not settle the training question**, which is a separate
  clause and still open below.
- ~~**The canonical Vertex terms.**~~ **No longer blocking, decided 2026-08-12:
  accepted for a synthetic corpus with a tripwire, exactly like residency above.**
  A no-training clause protects confidential content and there is none here — 40
  generated documents about invented suppliers. **Reading the terms is still owed
  before a real document is sent**, and any document not generated by this repo
  entering `corpus/sources/` voids the acceptance. It also costs ADR-0009 something
  real, recorded there: the free-tier/paid split was justified on data terms, so on
  a synthetic corpus `EXTRACT` is on Vertex for rate limits and a credential, not
  for data protection. **The research below stays** — it is what someone with a
  browser needs, and it is still unfinished.
  **Retried 2026-08-09 and narrowed, not resolved:** `cloud.google.com/terms/service-terms`
  *does* load now — the earlier "would not load" is stale — but the fetched text
  carries no Vertex or generative-AI clause at all, only data location (§1) and
  Pre-GA terms (§5). The data-governance page has moved to
  `docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance` and returns
  only its navigation shell to a fetcher, because the body is client-rendered. **So
  it needs a browser, not a tool** — and the specific thing to look for is the
  "Zero Data Retention" section that page's title advertises.

  **Retried again 2026-08-11, three fetches, narrowed a third time and still not
  resolved. Two of the three findings change where to look:**

  - The data-governance page still returns navigation only. Confirmed, not assumed
    — the "needs a browser" note above is current, not stale.
  - **The Service Specific Terms cross-reference a section named "AI/ML Data
    Location" at §1(b)(ii), whose body is not on the page fetched.** That is a
    name to search for rather than a topic to hunt. But note what it is: *data
    location*, which answers the residency question above and **not** the training
    question ADR-0009 rests on. They are separate clauses and were being looked
    for as one.
  - **The Cloud Data Processing Addendum contains no explicit "we will not train"
    clause.** What it has is §5.2, a purpose limitation: Google processes Customer
    Data "only ... to provide, secure, and monitor the Services" plus the
    customer's own instructions. Training a foundation model is not providing the
    Services, so the commitment appears to be *implied by purpose limitation
    rather than stated*. Appendix 4 (Specific Products) was not in the fetched
    text and is the next place to look.

  **This sharpens the caution rather than relieving it.** ADR-0009 says customer
  data "stays out of the foundation model training corpus", and the explicit
  sentence saying so has now failed to turn up in three canonical documents. It
  may still exist in Appendix 4 or behind the client-rendered page. What can be
  said today is weaker than what the ADR says, and the ADR should be read as
  resting on a purpose limitation plus product documentation until someone opens
  a browser and finds better.
- ~~**Whether the corpus covers perishables.**~~ **Closed 2026-08-12: no, the cut
  stands.** The seed has perishable *categories* — Fruits & Vegetables, Dairy &
  Paneer, Biscuits & Bakery — and a `policy-cold-chain` document, but
  `002_categories.csv` is `category_id, name, department` and **there is no
  shelf-life or expiry field anywhere in the schema**. Near-expiry pricing has
  nothing to key off, so building it means a migration plus a seed regeneration,
  and regenerating the seed voids every eval expected result set. Recorded so it is
  not re-asked from the category names alone, which is what makes it look open.
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
