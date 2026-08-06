# ADR-0004: Numbered SQL migrations, not Alembic

Date: 2026-08-05
Status: Accepted

## Context

Small schema, no production database, a seed generator that must stay
reproducible, and pgvector in the stack.

## Decision

`migrations/001_core_schema.sql` … `00N_*.sql`, applied in order by `make db`. No
down-migrations. `make db` resets.

Seed data is generated in Python with `random.Random(42)`, written to CSVs, and
`COPY`d in.

## Alternative rejected

Alembic.

## Why

1. **Alembic exists to evolve a database you can't drop.** This one is always
   droppable.
2. **There is no ORM for autogenerate to diff against**, so every migration would
   be hand-written SQL anyway — Alembic adds revision-chain overhead for nothing.
3. **pgvector makes it worse:** HNSW index creation with `vector_cosine_ops` ends
   up inside `op.execute()` raw SQL regardless.
4. **A reviewer reads one file and understands the data model.** Alembic requires
   reconstructing it from a chain.

## Determinism notes

- Seed generation is **Python-side**. SQL `random()` is not reproducible across
  Postgres versions, and Python-side generation makes the seed CSVs committable
  artifacts.
- **`ORDER BY` wherever order matters.** Postgres guarantees no row order without
  it; unstable ordering silently changes eval scores.

## Known cost

`agent_runs` and `proposed_actions` will change shape repeatedly during Phase 4,
and with no down-migrations that means `make db` each time. Mitigation: keep a
full reset under ~15 seconds, with `SEED_SIZE=small` for development and `full`
for the demo build.

## What would flip it

Nothing foreseeable at this scale. A real deployment with data worth preserving
would.