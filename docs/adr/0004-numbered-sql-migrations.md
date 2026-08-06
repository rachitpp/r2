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
and with no down-migrations that means rebuilding each time.

**Mitigation, measured in Phase 0.** The rebuild is split in two, which is also
the test-isolation mechanism ADR-0005 asks for:

| | What it does | `small` | `full` |
|---|---|---|---|
| `make db` | migrations, `COPY`, refresh, mark template | 13s | 60s |
| `make reset` | `CREATE DATABASE … TEMPLATE` — a file copy | 1.8s | 5.6s |

The original target was a full reset under ~15 seconds. `make db` at `full`
misses that at 60s, and it does not matter: `make db` only runs when the schema
or the seed changes. The loop that runs constantly — after every migration edit
in Phase 4, and once per test that needs isolation — is `make reset`, which is
seconds at any size because Postgres copies the template's files rather than
replaying the load. Sizing the seed is therefore not constrained by reset speed.

`SEED_SIZE=small` remains the development default and `full` the demo build.
They are independent datasets, not subset and superset; every eval runs against
`full`.

## What would flip it

Nothing foreseeable at this scale. A real deployment with data worth preserving
would.