# Conventions

How to work in this repo.

## Working style

- **Propose before writing more than ~100 lines.** Sketch the shape — file names,
  signatures, data flow — and wait. This is the main lever I have for keeping the
  design mine.
- **Commit at phase boundaries**, and at meaningful checkpoints inside a phase.
  Not every file write. Message format: `phase N: what changed`.
- **Never end a session with the system broken.** Time on this project is
  irregular; the gap between sessions may be weeks. If a session runs out mid-way
  through something, revert to the last working state or leave it behind a flag —
  and say so in `PROGRESS.md`. A red build is how this project dies.
- **Run `ruff check`, `ruff format`, and (if `web/` was touched) `npm run lint`
  before saying you're finished.** Not after I ask.
- **Update `docs/PROGRESS.md` as the last action of every session.** Before you
  run out of room, not after.
- **Don't refactor adjacent code you weren't asked to touch.** Mention it instead.
- If something on the cut list looks necessary, say so and stop. Don't build it.

## Where files go

    api/             FastAPI app, agent loop, ingestion, tools
      prompts/       Prompt files — see ADR-0008. Never inline a prompt.
        context/     business_context.md, schema.md — injected, not duplicated
      pyproject.toml  uv.lock  .python-version
      src/           Application code — layout decided by proposal
      tests/         pytest only
      scripts/       Seed generator, scoring, eval runners
    web/             Next.js + Tailwind, TypeScript
      package.json  package-lock.json
    corpus/          Real documents and pipeline output. See CLAUDE.md rule 8.
      sources/       contracts/ policies/ invoices/ catalogs/
      parsed/        Docling output — committed
      extracted/     Raw schema-guided extraction — committed, never hand-edited
      corrections/   Hand-fixed deltas, one note per fix
      gold/          Hand-labeled ground truth
      injection/     Specimens + full traces, one dir per specimen
      README.md  MANIFEST.csv  TIMELINE.md  KNOWN_ISSUES.md
      CHECKSUMS.txt  PIPELINE.json
    evals/           Question sets and results — committed
      sql/questions.jsonl       30-50 questions + expected result sets
      results/                  Dated JSON, one per run, with prompt hashes
    migrations/      001_*.sql, 002_*.sql — numbered, applied in order
    demo/            trajectories/ — cached runs for DEMO_MODE
    docs/            PLAN.md CONVENTIONS.md PROGRESS.md adr/
    README.md        Top-level. Results block stays current.

## Database

- **Numbered SQL migrations. Never Alembic** (ADR-0004). `migrations/00N_name.sql`,
  applied in order by `make db`.
- No down-migrations. The database is always droppable; `make db` resets.
- **Every table and column gets a `COMMENT ON`, and any migration is followed by
  `make schema-doc` in the same commit.** `api/prompts/context/schema.md` is
  generated from those comments and is injected into every SQL prompt, so a
  stale one feeds the model documentation that no longer matches the database —
  which is the most productive source of confidently-wrong SQL there is. CI
  fails when the committed copy is stale, but catching it at commit time is the
  point. `business_context.md` next door is hand-written; nothing generates it.
- **`ORDER BY` anywhere order matters.** Postgres guarantees nothing without it,
  and unstable ordering silently changes eval scores.
- Seed generation happens in Python with `random.Random(42)`, writes CSVs, then
  `COPY`s them in. The CSVs are committable artifacts.
- Keep a full reset under ~15 seconds. `SEED_SIZE=small` for development, `full`
  for the demo build.
- Two roles: an app role, and a read-only role with an enforced `LIMIT` that all
  generated SQL runs under.

## API and agent

- FastAPI, **JSON + SSE only**. No templates, no server-rendered HTML (ADR-0007).
- Tool argument schemas and API request schemas are **the same Pydantic models**.
  Don't maintain two sets.
- **Never run an agent inside a request handler.** `POST /runs` inserts an
  `agent_runs` row and returns `run_id` immediately. A separate worker claims work
  with `SELECT ... FOR UPDATE SKIP LOCKED`. The web app subscribes via SSE at
  `GET /runs/{id}/events`.
- No Celery, no Redis, no broker. The claim loop is ~40 lines.
- Agent state lives in Postgres rows, not in process memory (ADR-0003).
- Model selection goes through role config — `PLAN`, `EXTRACT`, `CLASSIFY` —
  resolved from env. Never hardcode a model string at a call site.
- `DEMO_MODE` is API-side only. The web app must not know whether a run is live or
  replayed.
- Generate `web/src/lib/api-types.ts` from the FastAPI OpenAPI schema rather than
  hand-writing types twice.

## Prompts

**Prompts are files in `api/prompts/`, never strings in Python** (ADR-0008). No
f-string prompt construction at call sites, ever. If a prompt needs a new input,
add a placeholder and document it in `api/prompts/README.md`.

- Substitution is `str.format()` with named placeholders. No templating library.
- Literal braces in prompt body text must be doubled.
- Domain documentation goes in `api/prompts/context/` and is injected as a
  placeholder — never copy-pasted into multiple prompts.
- **Untrusted content goes below all instructions, inside a delimited block**, and
  the prompt states that the block is data. `retrieval_answer.md` is the reference
  structure; copy it rather than inventing a variant.
- Write `context/business_context.md` before any prompt engineering. It is the
  highest-return work in Phase 1 (ADR-0001).

**Eval results record prompt hashes.** Every `make eval-*` run writes the SHA-256
of each prompt file it used into `evals/results/<date>-<suite>.json` alongside the
scores. Changing a prompt without re-running the relevant eval leaves a stale
number in the README — re-run it, or mark it stale in `PROGRESS.md`.

## Frontend

Next.js App Router, TypeScript, Tailwind. Keep it thin: fetch in server components
where possible, `useState` where not, one typed fetch wrapper. **No Redux, no
Zustand, no React Query** unless something concrete demands it and I've agreed.

### Design tokens come before components

Before writing any component, produce a short design plan and show it to me:

- **Color** — 4–6 named hex values, defined in `tailwind.config.ts` as a custom
  palette. Do not use Tailwind's default `gray-500` / `blue-600` scale.
- **Type** — at least two roles: a characterful display face used with restraint,
  and a complementary body face. A utility face for data and captions if needed.
  Set an intentional scale with deliberate weights. Type is the personality of the
  interface, not a delivery vehicle.
- **Layout** — one-sentence concept plus an ASCII wireframe for the approval card
  and the audit log.
- **Signature** — the one element this interface is remembered by. It should be
  the approval card.

**Three looks to avoid**, because they read as AI-default regardless of subject:
warm cream background with high-contrast serif and terracotta accent; near-black
with a single acid-green or vermilion accent; broadsheet layout with hairline
rules and zero border-radius. Any of them may be right for some brief — but pick
them as a choice, not a fallback.

### Spend boldness in one place

The approval card is the signature; everything around it stays quiet. Make it
information-dense: the agent's written reasoning, the inputs it used, the spending
cap it checked against, a live expiry countdown, and a stale-input warning when
the underlying price has moved since drafting. The audit log should read like a
ledger.

### Interface copy is design material

- **Active voice, and the control says what happens.** "Approve order", not
  "Submit".
- **An action keeps its name through the whole flow.** The button that says
  "Approve" produces a state that says "Approved" and an audit line that says
  "Approved". Vocabulary is how someone learns their way around.
- **Errors explain what went wrong and how to fix it.** They don't apologise and
  they're never vague. "This proposal expired 2 hours ago. Re-run to draft a
  current one."
- **Empty states are an invitation to act**, not a mood. "No proposals waiting.
  Run the procurement agent to draft one."
- Name things by what the person controls, never by how the system is built.

### Quality floor, unannounced

Responsive down to mobile. Visible keyboard focus. `prefers-reduced-motion`
respected. Don't add animation that doesn't serve the interface — scattered
transitions are themselves a tell.

## Tests and evals

- **pytest asserts. Evals measure. They are different things** (ADR-0005).
- Evals are `make eval-extraction` and `make eval-sql`, run at phase boundaries.
  **Never in pytest, never in CI** — they cost quota.

### Stage 1 is a permanent gate, not a one-time ramp

**Before any full eval run: five questions, one run, and read every failure by
hand.** Only then the full set at one run, only then three.

    make eval-sql EVAL_ARGS="--limit 5 --runs 1"

This is not caution about spend. **An eval set cannot be validated by
inspection, only by use.** The first staged run of the SQL set scored 0/4, and
none of it was the model: every reference query carried an arbitrary `LIMIT`
the question had never asked for, and one contradicted the generation prompt's
own rule about store scope. All 45 questions had been read, reviewed and
cross-checked against second queries beforehand. They still looked fine on the
page. Seven model calls found what no amount of rereading had.

Two rules that follow:

- **Re-run stage 1 on questions that were not in the previous stage 1.**
  Re-testing the ones just diagnosed proves only that those were fixed.
- **A staged run that fails is not a result.** Do not write it to
  `evals/results/`, and do not quote the number. Diagnose first; a published
  0% that turns out to be an instrument bug is worse than no number.

Defects found this way go in `evals/README.md`, which plays the same role for
the eval set that `corpus/KNOWN_ISSUES.md` plays for the corpus.
- pytest covers pure functions (date resolution, chunk boundaries, scoring) and DB
  integration via `CREATE DATABASE test_x TEMPLATE seeded_template`.
- `ruff` for lint and format. mypy optional, does not gate CI.
- Frontend: `tsc --noEmit` and `next lint`. No component test suite — not worth
  the hours at this scale.

## CI

Runs on every push with **no API key present**. Two jobs.

**Python:**
- `make verify-corpus` — SHA-256 every file in `parsed/` and `extracted/` against
  `corpus/CHECKSUMS.txt`.
- `make verify-parse` — re-run Docling on a committed 3-document sample and assert
  byte-identity. Local, no network, no key.
- `pytest`, `ruff check`.

**Web:**
- `npm ci`, `tsc --noEmit`, `next lint`, `next build`.
- **Must pass without the API running.** No build-time fetches against localhost.

Full-pipeline determinism (`make ingest-verify`) is local and gated. See ADR-0006
for why the claim is scoped to the parse layer.

## Environment

- Python: `uv`. `api/pyproject.toml`, `api/uv.lock`, `api/.python-version` all
  committed.
- Web: `npm`. `package-lock.json` committed. Pin the Node major in `.nvmrc`.
- `docker compose up` is the real reproduction path — pgvector extension plus
  Docling weights make it so. DB image: `pgvector/pgvector:pg16`.
- Services: `db`, `api`, `worker`, `web`. Ollama behind `--profile local-models`,
  **default off**, with model-role config falling back to API when the local
  service isn't reachable rather than crashing.
- `.env.example` committed, `.env` gitignored. Startup check fails loudly with a
  useful message when config is missing.
- `DEMO_MODE=true` is the compose default. Demo trajectories load through the same
  API code path that would call the model — real UI, real data, replayed runs. Not
  mocks.
- Langfuse self-hosted, and tracing degrades to a no-op when unconfigured.