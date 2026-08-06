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
      extract_contract.md      Schema-guided extraction   [Phase 2]
      extract_invoice.md                                  [Phase 2]
      extract_policy.md                                   [Phase 2]
      extract_catalog.md                                  [Phase 2]
      retrieval_answer.md      Retrieved chunks → answer  [Phase 3]
      agent_plan.md            Procurement agent system   [Phase 4]

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

Every literal brace in prompt body text must be doubled: `{{` and `}}`.

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