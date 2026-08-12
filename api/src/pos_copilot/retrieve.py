"""Date- and role-filtered vector retrieval over `doc_chunks`.

**Rule 5: role scope is applied BEFORE generation, never after.** That is a
statement about SQL, not about intent — the scope predicate is part of the
retrieval query's WHERE clause, so a chunk the caller may not see is never
fetched, never ranked, and never reaches the prompt. Filtering results
afterwards would leave the row in memory and one refactor away from a leak.

**Rule 7: the date filter is also pre-generation.** Every chunk carries its own
`valid_period`, so "what were the terms before the renegotiation" is answered by
restricting the candidate set to the documents in force on that date, not by
retrieving everything and asking the model to sort out the chronology. The
second approach cannot distinguish a correct historical answer from a plausible
invented one, which is the failure demo beat 2 exists to show.

**"No document in force" is not "not found".** They are different answers to
different questions and `retrieval_answer.md` is written to say which applies.
`retrieve()` therefore reports which case it is in rather than returning an empty
list and leaving the caller to guess — see `Retrieval.outcome`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Exact scan, no ANN index. A few hundred chunks makes this both faster than an
# index probe and exactly reproducible; see migrations/004_retrieval.sql.
DEFAULT_LIMIT = 6


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    doc_type: str
    chunk_index: int
    content: str
    effective_from: date
    effective_to: date | None
    similarity: float

    def citation(self) -> str:
        """The format `retrieval_answer.md` asks for."""
        return f"[{self.doc_id}, effective {self.effective_from}]"


@dataclass(frozen=True)
class Retrieval:
    chunks: list[Chunk]
    outcome: str  # "found" | "none_in_force" | "not_found"
    as_of: date

    @property
    def found(self) -> bool:
        return self.outcome == "found"


def store_scope_for(role: str, store_id: int | None) -> int | None:
    """Which store this request may see documents for. `None` means chain-wide.

    Deliberately the same shape and the same refusal as
    `readonly_sql.visible_stores`, because a reader who has understood scoping
    on the SQL path should not have to learn a second set of rules here. A
    store-scoped role with no store raises rather than defaulting: a defaulted
    store is the wrong shop's invoices wearing the right shop's label.
    """
    from .readonly_sql import UNSCOPED_ROLES, StoreRequired

    if role in UNSCOPED_ROLES:
        return None
    if store_id is None:
        raise StoreRequired(
            "this request runs as a store-scoped role and no store was given. "
            "Picking one would retrieve the wrong shop's documents without "
            "saying so."
        )
    return store_id


def _scope_sql(supplier_id: int | None, store_id: int | None) -> tuple[str, list]:
    """Build the scope predicate.

    A NULL `supplier_id` on a chunk means "not supplier-specific" — a policy
    applies chain-wide. So a supplier-scoped query must match its own supplier
    OR NULL; matching only the supplier drops every policy document silently,
    which reads as the corpus being thin rather than the filter being wrong.
    """
    clauses: list[str] = []
    params: list = []
    if supplier_id is not None:
        clauses.append("(c.supplier_id = %s OR c.supplier_id IS NULL)")
        params.append(supplier_id)
    if store_id is not None:
        clauses.append("(c.store_id = %s OR c.store_id IS NULL)")
        params.append(store_id)
    return (" AND ".join(clauses) if clauses else "TRUE"), params


def retrieve(
    conn,
    query: str,
    *,
    as_of: date,
    embedder,
    supplier_id: int | None = None,
    store_id: int | None = None,
    doc_types: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Retrieval:
    """Return the chunks in force at `as_of` that best match `query`.

    The vector is computed with BGE's query prefix; the documents were embedded
    without it, which is what that model expects. Doing the same to both sides
    is a silent retrieval loss.
    """
    vector = embedder.encode_one(query, is_query=True)
    scope_sql, scope_params = _scope_sql(supplier_id, store_id)

    type_sql = "TRUE"
    type_params: list = []
    if doc_types:
        type_sql = "c.doc_type = ANY(%s)"
        type_params = [doc_types]

    sql = f"""
        SELECT c.doc_id, c.doc_type, c.chunk_index, c.content,
               c.effective_from, c.effective_to,
               1 - (c.embedding <=> %s::vector) AS similarity
          FROM doc_chunks c
         WHERE c.embedding IS NOT NULL
           AND c.valid_period @> %s::date
           AND {scope_sql}
           AND {type_sql}
         ORDER BY c.embedding <=> %s::vector
         LIMIT %s
    """
    params = [str(vector), as_of, *scope_params, *type_params, str(vector), limit]

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if rows:
        chunks = [
            Chunk(
                doc_id=r[0],
                doc_type=r[1],
                chunk_index=r[2],
                content=r[3],
                effective_from=r[4],
                effective_to=r[5],
                similarity=float(r[6]),
            )
            for r in rows
        ]
        return Retrieval(chunks=chunks, outcome="found", as_of=as_of)

    # Nothing in force. Distinguish "there are documents, none covering this
    # date" from "there are no documents at all for this scope" — the same scope
    # filter, without the date, answers it. Demo beat 2 is exactly this.
    probe = f"""
        SELECT count(*) FROM doc_chunks c
         WHERE c.embedding IS NOT NULL AND {scope_sql} AND {type_sql}
    """
    with conn.cursor() as cur:
        cur.execute(probe, [*scope_params, *type_params])
        any_at_all = cur.fetchone()[0]

    outcome = "none_in_force" if any_at_all else "not_found"
    return Retrieval(chunks=[], outcome=outcome, as_of=as_of)


def format_documents(retrieval: Retrieval) -> str:
    """Render chunks for the DOCUMENTS block of `retrieval_answer.md`.

    Content goes in as data with its provenance attached, and nothing here
    interpolates a chunk into an instruction (rule 6). The prompt's delimiters
    and security section are what make this safe; this function's job is only to
    make each chunk citable.
    """
    if not retrieval.chunks:
        return "(no documents were in force at that date)"
    parts = []
    for chunk in retrieval.chunks:
        until = chunk.effective_to or "further notice"
        parts.append(
            f"--- {chunk.doc_id} "
            f"(effective {chunk.effective_from} until {until}) ---\n"
            f"{chunk.content}"
        )
    return "\n\n".join(parts)


def clauses_in_force(conn, supplier_id: int, on: date) -> list[dict]:
    """The clause-level view: what each document SAYS, latest statement wins.

    This is what `supplier_term_clauses` is for and what `supplier_terms` cannot
    answer. An amendment states three clauses; the rest of the set is inherited
    from the agreement it varies, so "in force" is computed over the chain here
    rather than being asserted by a single wide row.

    `DISTINCT ON` takes the most recently effective statement of each clause,
    which is the inheritance rule written once in SQL instead of being performed
    by a model per query — the failure mode Phase 2's amendments demonstrated.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (clause)
                   clause, clause_number, value_numeric, value_text,
                   verbatim, doc_id, effective_from
              FROM supplier_term_clauses
             WHERE supplier_id = %s AND valid_period @> %s::date
             ORDER BY clause, effective_from DESC
            """,
            (supplier_id, on),
        )
        return [
            {
                "clause": r[0],
                "clause_number": r[1],
                "value": r[2] if r[2] is not None else r[3],
                "verbatim": r[4],
                "doc_id": r[5],
                "effective_from": r[6],
            }
            for r in cur.fetchall()
        ]
