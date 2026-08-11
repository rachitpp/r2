# Prompts

Prompts are **files, not strings**. See [ADR-0008](../../docs/adr/0008-prompts-as-files.md).

Never inline a prompt in Python. Never build one with f-string concatenation at a
call site. Every prompt in this project lives here, is loaded at runtime, and is
diffable in git.

## Layout

    prompts/
      context/
        business_context.md    Domain vocabulary, metric definitions, gotchas
        schema.md              Table and column documentation
      sql_generate.md          NL question → SQL          [Phase 1]
      sql_answer.md            Result set → prose answer  [Phase 1]
      extract.md               Schema-guided extraction   [Phase 2]
      retrieval_answer.md      Retrieved chunks → answer  [Phase 3]
      agent_plan.md            Procurement agent system   [Phase 4]

**One extraction prompt, not four.** This file planned
`extract_contract.md` / `_invoice.md` / `_policy.md` / `_catalog.md`. What differs
between the four document types is only the JSON shape being asked for; the rules
about recording nothing the document does not state, and the security block
saying document text is data, are identical. Four copies would mean fixing an
injection defence in four places and finding out later that one was missed —
which is the reason `context/` is injected rather than pasted. The per-type shape
lives in `pos_copilot.extract.SCHEMAS` and arrives through `{json_schema}`, and
the same module validates the response against it, so the schema shown and the
schema enforced cannot drift.

**`extract.md` injects no `context/` files, deliberately.** `business_context.md`
and `schema.md` describe the database, and extraction is measured on recording
what a document says rather than what the database expects it to say — handing
the model the answers would corrupt the measurement. It also means the extraction
fingerprint is independent of both, so the corrections gated in `docs/HANDOFF.md`
can land without voiding a single extracted document. `test_extract.py` asserts
this rather than trusting it.

`context/` files are not prompts — they are documentation injected *into* prompts.
`business_context.md` is the single highest-leverage artifact in the repo
(ADR-0001) and should be written before any prompt engineering.

## Placeholder contract

Substitution uses `str.format()` with named placeholders. No templating
dependency.

    {question}          User's natural language question
    {schema}            Contents of context/schema.md
    {business_context}  Contents of context/business_context.md
    {retrieved}         Retrieved document chunks, pre-formatted
    {result_rows}       Query result set, pre-formatted
    {as_of_date}        Date the query is scoped to
    {tool_schemas}      JSON tool definitions
    {user_role}         Role the request runs under
    {store_scope}       Stores this user may see: "all stores", or a single
                        store named as "store_id = 3 (Dharampeth, Nagpur)"
    {doc_type}          contract | invoice | catalog | policy
    {doc_id}            MANIFEST.csv doc_id of the document being extracted
    {json_schema}       The shape to return, from pos_copilot.extract.SCHEMAS
    {document}          Parsed document text from corpus/parsed/, untrusted

Every literal brace in prompt body text must be doubled: `{{` and `}}`.

## "Today" means the anchor date, not wall-clock

The seed data has a fixed end date so it can be byte-identical on re-run
(`DATA_END_DATE` in `api/scripts/seed.py`, mirrored by `AS_OF_DATE` in `.env`).
So `current_date` is not today as far as this system is concerned, and SQL that
uses it silently returns nothing once wall-clock passes the anchor.

`{as_of_date}` is supplied to `sql_generate.md` and `retrieval_answer.md` for
this reason, and **`context/business_context.md` must state it explicitly** —
that relative periods resolve against the anchor, and that `current_date`,
`now()` and `CURRENT_TIMESTAMP` are never correct in generated SQL. A rule in
one prompt is a rule the other prompts do not get; the context document is
where it belongs.

Eval expected result sets are computed against the same anchor. One written
against wall-clock rots within 30 days.

## Two refusal sentinels, and they are not interchangeable

    -- INSUFFICIENT SCHEMA: <what is missing>
    -- OUT OF SCOPE: this user can only see <scope>

The first means the database cannot answer the question for anyone. The second
means it can, but not for this user.

They are scored as separate categories in `evals/sql/questions.jsonl`. Folding
them together would make one number measure two unrelated capabilities —
knowing the limits of the schema, and honouring an authorization boundary — and
a model could then look competent at one by being good at the other.

## `context/schema.md` is generated, not written

`make schema-doc` builds it from the `COMMENT ON` statements in
`migrations/001_core_schema.sql`, and CI fails if the committed copy is stale. A
hand-maintained schema document drifts from the schema, and a drifted schema
document is the most productive source of confidently-wrong SQL there is.

`business_context.md` is the opposite: hand-written, and the
highest-leverage artifact in the repo (ADR-0001). Nothing generates it.

## Structural rule: data is never instruction

Retrieved document content, query results, and user input go inside a clearly
delimited block, **below** all instructions, and every prompt that receives
untrusted content says so explicitly. `retrieval_answer.md` is the reference
implementation — copy its structure.

There is exactly one deliberate violation: the `--unsafe` path used to
demonstrate the injection attack working. It lives in code, is labelled, and is
never the default.

## Versioning

Prompt changes move eval scores. Every eval run records the SHA-256 of each
prompt file it used, written into `evals/results/`. When a README number moves,
the hash tells you whether the prompt moved with it.

    make prompt-hashes    # print current hashes

Changing a prompt without re-running the relevant eval leaves a stale number in
the README. Either re-run it or mark it stale.