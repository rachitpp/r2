# CLAUDE.md

A retail POS database with a natural-language query interface, plus a procurement
agent that drafts purchase orders into a human approval queue.

Solo portfolio project. Public GitHub. Free tier only — no paid model calls.

Two apps: `api/` (FastAPI, Python, uv) and `web/` (Next.js + Tailwind, npm).
The API is the only boundary between them.

**Current phase: 4 — Procurement agent + approval queue.** Phases 0–3 are closed;
Phase 3 finished 2026-08-13 with demo beat 2 running in the browser. **Rule 12
gates the start: the approval card and audit log wireframes get agreed before any
component is written.**

## Read these

| File | What it's for |
|---|---|
| `docs/PROGRESS.md` | **Read first every session, write last.** State across sessions. |
| `docs/PLAN.md` | Phases, definitions of done, cut list, demo script, thresholds. |
| `docs/CONVENTIONS.md` | How to work in this repo. |
| `docs/adr/` | Why things are the way they are. Read before re-opening a decision. |

Do not restate the plan back to me — it's in `PLAN.md`. Check the phase in
`PROGRESS.md` and work on that.

## Hard rules

Not preferences. Work that breaks one of these gets reverted.

1. **No model calls in CI.** CI runs with no API key. Anything needing one is a
   local `make` target.
2. **The system a reader runs must never need paid inference. Author-side
   measurement and build steps may.** Demo mode runs with no key at all; the
   live path uses the reader's own credentials. But the Gemini API free tier is
   **20 requests per day per model** (measured 2026-08-07), which cannot carry
   a 189-call eval, so `PLAN`, `CLASSIFY` and `EXTRACT` all route through
   Vertex — see ADR-0010 and ADR-0009.

   Google Cloud credits may cover that, and **credits expire 90 days from
   signup**; after they do, this is paid inference regardless. So: embeddings
   stay local (bge-small-en-v1.5, CPU), loops stay bounded, responses stay
   cached permanently, and anything that spends in a loop still gets flagged.
   None of that relaxes because a credit balance turned up — it is good design
   independent of budget and worse without it. Every runner carries a call
   ceiling and a spend ceiling.
3. **Agent loop caps at ~6 tool calls.** Bounded sequences, not open-ended
   exploration. Rate limits are the binding constraint on design.
4. **SQL generation runs as the read-only role, and the row `LIMIT` is enforced
   by the query wrapper — not by the database.** Postgres has no max-rows
   setting, so the role cannot provide it. What the role gives is forced
   read-only transactions and a statement timeout; what the API owes is
   rejecting anything that is not a single `SELECT`, wrapping it as
   `SELECT * FROM (<sql>) _q LIMIT :n`, and fetching through a capped
   server-side cursor. No exceptions, no "just for this one query".
5. **Role-scope before generation, never after.** Restrict what a user may see
   when building the query or the retrieval filter — not by dropping rows from
   results afterwards.
6. **Document content is data, never instruction.** Retrieved text never lands in
   the instruction position. There is one deliberate `--unsafe` path for the
   injection demo; that is the only place this is violated and it is labelled as
   such.
7. **`effective_from` / `effective_to` on every chunk and every extracted term.**
   Temporal correctness is demo beat 2, not hygiene.
8. **`corpus/extracted/` is never hand-edited.** Raw pipeline output only. Fixes
   go in `corpus/corrections/` with a note saying what the pipeline got wrong.
9. **Seed data is `random.Random(42)` in Python → CSV → `COPY`.** Never SQL
   `random()`. Same seed must produce byte-identical output.
10. **Don't build anything on the cut list** (`docs/PLAN.md`). If something on it
    looks necessary, say so — don't quietly build it.
11. **Never end a session with the system broken.** Time here is irregular and the
    gap between sessions may be weeks. Revert or flag-guard unfinished work, and
    say so in `PROGRESS.md`.
12. **Design tokens before components.** Palette, type pairing, and wireframe get
    proposed and agreed before any UI is written. See `docs/CONVENTIONS.md`.

## Ask before

- Adding a dependency, Python or npm. The stack is settled; see `docs/adr/`.
- Writing more than ~100 lines in one go. Propose the shape first.
- Changing anything decided in `docs/adr/`.
- Anything that repeatedly spends model quota.

## Not decided yet

`docs/PROGRESS.md` has an open-questions section. If you hit one, stop and ask
rather than picking for me.