# ADR-0008: Prompts are files, not strings

Date: 2026-08-06
Status: Accepted

## Context

This project has roughly nine distinct prompts across text-to-SQL, four extraction
schemas, grounded retrieval, and agent planning. Two properties of the project
depend on how they are stored.

**Measurement.** The README publishes accuracy numbers. Those numbers are only
meaningful if it is knowable which prompt produced them. ADR-0005 and ADR-0006
both rest on published numbers being traceable.

**Inspectability.** The prompts are among the more interesting artifacts here — the
injection defence is *structural*, expressed in how the prompt is laid out. A
reviewer should be able to read that without reading Python.

The default behaviour, absent a rule, is f-strings at the call site. That makes
prompts undiffable, unversionable, and invisible.

## Decision

Every prompt lives in `api/prompts/` as a `.md` file, loaded at runtime.

- Substitution via `str.format()` with named placeholders. No templating
  dependency.
- Domain documentation (`business_context.md`, `schema.md`) lives in
  `api/prompts/context/` and is injected as a placeholder, not duplicated across
  prompts.
- Untrusted content goes in a delimited block below all instructions, in every
  prompt that receives it. `retrieval_answer.md` is the reference structure.
- Every eval run records the SHA-256 of each prompt file it used into
  `evals/results/`.

## Alternatives rejected

**F-strings at the call site.** Undiffable, and a prompt change becomes
indistinguishable from a logic change in review.

**A prompt-management service** (Langfuse prompt management, PromptLayer, etc.).
Adds a network dependency and an account to a project that must run with no API
key. Git already does versioning.

**Jinja2 for templating.** Jinja2 was removed from this stack with the frontend
decision (ADR-0007). Re-adding it for nine prompts with simple substitution is not
worth a dependency. Revisit only if prompts need loops or conditionals.

## Why it matters more than it looks

Without prompt hashes in eval results, the README numbers rot silently. Someone
tweaks a prompt in Phase 4, never re-runs the Phase 1 eval, and the published
accuracy figure now describes a prompt that no longer exists. That is exactly the
kind of quiet dishonesty ADR-0006 exists to prevent.

## What would flip it

Prompts needing real conditional logic — at which point Jinja2 earns its
dependency. Simple substitution does not.
