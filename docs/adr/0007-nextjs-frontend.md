# ADR-0007: Next.js + Tailwind frontend, separate from the API

Date: 2026-08-06
Status: Accepted

## Context

The stack decision that preceded this repo chose server-rendered Jinja2 + HTMX, on
the grounds that the polish budget for the approval interface is a *design*
budget, not a framework budget, and an SPA spends those hours on build config and
client state that no reviewer ever sees. That direction was never written up as
its own ADR; this supersedes it.

The reasoning was sound and is overridden by a stated preference: Next.js with
Tailwind. That is a legitimate reason to override it. Framework choice on a
portfolio project is partly a signalling decision, and the roles this project
targets are more likely to name React and Next.js than HTMX.

## Decision

Two applications in one repo.

- `api/` — FastAPI, JSON + SSE only. No templates, no server-rendered HTML.
- `web/` — Next.js (App Router) + Tailwind, TypeScript.

The API is the sole boundary. `DEMO_MODE` stays an API-side concern; the web app
does not know whether a run is live or replayed, which keeps demo mode from
leaking into two codebases.

## Alternative rejected

Jinja2 + HTMX, server-rendered from the same FastAPI process.

## Why the earlier reasoning still constrains this

Adopting an SPA does not suspend the point the earlier decision was making. Two
things carry over as binding:

1. **The approval card is still where the design effort goes.** Tailwind makes it
   easier to produce something that looks like every other Tailwind project. The
   defence is a token system defined *before* any component is written — see
   `docs/CONVENTIONS.md`.
2. **Don't spend the budget on architecture.** Server components, a state
   management library, and an ORM-style API client are all avoidable here. Fetch
   in server components where possible, `useState` where not, and a thin typed
   fetch wrapper. No Redux, no Zustand, no React Query unless something concrete
   demands it.

## Cost accepted

Roughly +12h: Next.js scaffold, typed API client, and SSE consumer land in Phase 1
(25h → 32h); the approval interface is more work in React than in HTMX in Phase 4
(32h → 38h); demo mode crosses a process boundary in Phase 5 (18h → 20h). First
demo moves from ~45h to ~52h. CI gains a frontend lint/typecheck/build job that
must pass without the API running.

## What would flip it

Nothing. This is a stated preference, and preference is a sufficient reason on a
portfolio project. Revisit only if the frontend starts consuming hours that the
agent and corpus work needs.