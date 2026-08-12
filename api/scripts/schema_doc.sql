-- Emits api/prompts/context/schema.md from the live database's own COMMENTs.
--
-- The schema documentation the model reads is generated from the schema rather
-- than written alongside it, because a hand-maintained schema.md drifts, and a
-- drifted schema.md is the most productive source of confidently-wrong SQL
-- there is (ADR-0001, threshold 1). business_context.md is the opposite case:
-- it is hand-written, and it is the highest-leverage artifact in the repo.
--
-- Run with:  psql -X -q -t -A -F '' -f schema_doc.sql

WITH objs AS (
    SELECT c.oid,
           c.relname,
           c.relkind,
           obj_description(c.oid, 'pg_class') AS descr,
           CASE c.relkind WHEN 'r' THEN 1 WHEN 'm' THEN 2 ELSE 3 END AS kind_ord
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'v', 'm')
      -- INFRASTRUCTURE, NOT BUSINESS DATA. This file generates the context the
      -- TEXT-TO-SQL model reads to answer questions about a shop, and these
      -- tables are not about a shop — they are how this project stores
      -- retrieval indexes and agent state.
      --
      -- Until 2026-08-13 there was no filter at all, so `doc_chunks` went into
      -- the SQL prompt complete with a `vector(384)` column the moment Phase 3
      -- landed, and the agent tables followed in Phase 4. Three costs, and the
      -- first is the one that matters:
      --
      --   1. Noise. ADR-0001's whole argument is that context does the work;
      --      the study the README cites moved GPT-4 from 8.3% to 78.3% on
      --      business context. Tables a question can never be about are the
      --      opposite of that, and `doc_chunks.embedding` is not queryable in
      --      any sense a user means.
      --   2. Every table added moves the prompt fingerprint and voids the eval
      --      cache.
      --   3. `pos_readonly` can SELECT these, so a model that sees them can
      --      write queries against them.
      --
      -- **The default is INCLUDE.** A new business table appears here without
      -- anyone remembering to add it, which is the failure worth avoiding; a
      -- new internal table shows up as noise until someone notices, which is
      -- visible rather than silent. Add to this list deliberately.
      --
      -- No eval question references any of them — checked, 0 of 49.
      AND c.relname NOT IN (
          'doc_chunks',        -- retrieval index (Phase 3)
          'agent_runs',        -- agent state (Phase 4)
          'proposed_actions',
          'agent_events'
      )
),
cols AS (
    SELECT a.attrelid,
           a.attnum,
           a.attname,
           format_type(a.atttypid, a.atttypmod) AS coltype,
           a.attnotnull,
           col_description(a.attrelid, a.attnum) AS descr
    FROM pg_attribute a
    WHERE a.attnum > 0 AND NOT a.attisdropped
),
fks AS (
    SELECT con.conrelid,
           unnest(con.conkey) AS attnum,
           (SELECT c2.relname FROM pg_class c2 WHERE c2.oid = con.confrelid) AS reftable
    FROM pg_constraint con
    WHERE con.contype = 'f'
),
pks AS (
    SELECT con.conrelid, unnest(con.conkey) AS attnum
    FROM pg_constraint con
    WHERE con.contype = 'p'
),
lines AS (
    SELECT o.kind_ord, o.relname, 0 AS ord, 0 AS sub,
           format('## `%s`%s', o.relname,
                  CASE o.relkind WHEN 'v' THEN ' — view'
                                 WHEN 'm' THEN ' — materialized view'
                                 ELSE '' END) AS line
    FROM objs o
    UNION ALL
    SELECT o.kind_ord, o.relname, 1, 0, '' FROM objs o
    UNION ALL
    SELECT o.kind_ord, o.relname, 2, 0, coalesce(o.descr, '_No description._')
    FROM objs o
    UNION ALL
    SELECT o.kind_ord, o.relname, 3, 0, '' FROM objs o
    UNION ALL
    SELECT o.kind_ord, o.relname, 4, 0, '| Column | Type | Key | Notes |' FROM objs o
    UNION ALL
    SELECT o.kind_ord, o.relname, 5, 0, '|---|---|---|---|' FROM objs o
    UNION ALL
    SELECT o.kind_ord, o.relname, 6, c.attnum,
           format('| `%s` | %s%s | %s | %s |',
                  c.attname,
                  c.coltype,
                  CASE WHEN c.attnotnull THEN ' NOT NULL' ELSE '' END,
                  CASE
                      WHEN p.attnum IS NOT NULL AND f.attnum IS NOT NULL
                          THEN 'PK, FK → ' || f.reftable
                      WHEN p.attnum IS NOT NULL THEN 'PK'
                      WHEN f.attnum IS NOT NULL THEN 'FK → ' || f.reftable
                      ELSE '' END,
                  coalesce(replace(c.descr, E'\n', ' '), ''))
    FROM objs o
    JOIN cols c ON c.attrelid = o.oid
    LEFT JOIN pks p ON p.conrelid = o.oid AND p.attnum = c.attnum
    LEFT JOIN fks f ON f.conrelid = o.oid AND f.attnum = c.attnum
    UNION ALL
    SELECT o.kind_ord, o.relname, 7, 0, '' FROM objs o
)
SELECT line FROM lines ORDER BY kind_ord, relname, ord, sub;
