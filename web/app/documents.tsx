"use client";

/**
 * Demo beat 2 — the same question, moved through time.
 *
 * The concept is one sentence: **the date is the variable, not the question.**
 * So the date control sits beside the answer rather than in a settings panel,
 * and the question stays put while the date moves. An interface that buried the
 * date would be demonstrating a search box.
 *
 * Three outcomes, and the UI must keep them apart:
 *
 *   answered        documents were in force; the answer cites them
 *   none_in_force   documents exist, none covering that date
 *   not_found       nothing at all for this scope
 *
 * `none_in_force` is the one worth building a view for. Rendering it as an
 * empty result would collapse it into `not_found`, and telling those two apart
 * is the entire point of the temporal schema underneath.
 */

import { useEffect, useState } from "react";
import {
  ApiError,
  AskResponse,
  Citation,
  DocQuestion,
  STORES,
  askDocuments,
  listDocQuestions,
} from "../lib/api";

const ROLES = ["owner", "manager", "clerk"] as const;
type Role = (typeof ROLES)[number];

export default function Documents() {
  const [catalogue, setCatalogue] = useState<DocQuestion[]>([]);
  const [question, setQuestion] = useState(
    "What are the payment terms for Sahyadri Agro Traders?",
  );
  const [asOf, setAsOf] = useState("2025-01-15");
  const [supplier, setSupplier] = useState("SUP-01");
  const [role, setRole] = useState<Role>("owner");
  const [storeId, setStoreId] = useState<number | "">("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listDocQuestions()
      .then(setCatalogue)
      .catch(() => setCatalogue([]));
  }, []);

  const scopedRole = role === "clerk";

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await askDocuments({
          question,
          as_of: asOf,
          role,
          store_id: storeId === "" ? null : storeId,
          supplier_code: supplier || null,
          doc_types: ["contract"],
        }),
      );
    } catch (caught) {
      setResult(null);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "the API is not reachable — is `make serve` running?",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <section className="rounded border border-rule bg-card p-4">
        <label htmlFor="docq" className="block text-[13px] font-medium">
          Ask the documents
        </label>
        <input
          id="docq"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          className="mt-1 w-full rounded border border-rule bg-white px-3 py-2 text-[15px]"
        />

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="asof" className="block text-[13px] font-medium">
              As of
            </label>
            <input
              id="asof"
              type="date"
              value={asOf}
              onChange={(event) => setAsOf(event.target.value)}
              className="mt-1 rounded border border-rule bg-white px-3 py-2 font-mono text-[15px]"
            />
          </div>

          <div>
            <label htmlFor="supplier" className="block text-[13px] font-medium">
              Supplier
            </label>
            <input
              id="supplier"
              value={supplier}
              onChange={(event) => setSupplier(event.target.value)}
              className="mt-1 w-28 rounded border border-rule bg-white px-3 py-2 font-mono text-[15px]"
            />
          </div>

          <div>
            <label htmlFor="role" className="block text-[13px] font-medium">
              Role
            </label>
            <select
              id="role"
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              className="mt-1 rounded border border-rule bg-white px-3 py-2 text-[15px]"
            >
              {ROLES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Shown only for a scoped role, and never pre-filled. The API
              refuses to pick a store rather than answer the wrong shop, so a
              default here would only move the guess one layer up. */}
          {scopedRole && (
            <div>
              <label htmlFor="docstore" className="block text-[13px] font-medium">
                Store <span className="text-oxide">required</span>
              </label>
              <select
                id="docstore"
                value={storeId}
                onChange={(event) =>
                  setStoreId(event.target.value === "" ? "" : Number(event.target.value))
                }
                className="mt-1 rounded border border-rule bg-white px-3 py-2 text-[15px]"
              >
                <option value="">choose…</option>
                {STORES.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            onClick={run}
            disabled={busy || !question.trim()}
            className="rounded bg-indigo px-4 py-2 text-[15px] font-medium text-white disabled:opacity-40"
          >
            {busy ? "Retrieving…" : "Ask"}
          </button>
        </div>

        {catalogue.length > 0 && (
          <p className="mt-3 text-[13px] text-brass">
            Demo mode replays these dates:{" "}
            {catalogue.map((entry, index) => (
              <button
                key={`${entry.question}-${entry.as_of}`}
                onClick={() => {
                  setQuestion(entry.question);
                  setAsOf(entry.as_of);
                  setSupplier(entry.supplier_code ?? "");
                }}
                className="underline decoration-dotted underline-offset-2"
              >
                {entry.as_of}
                {index < catalogue.length - 1 ? ", " : ""}
              </button>
            ))}
            . The date is part of the key — there is no nearest-date fallback.
          </p>
        )}
      </section>

      {error && (
        <p
          role="alert"
          className="mt-6 rounded border border-oxide/40 bg-card p-4 text-[15px] text-oxide"
        >
          {error}
        </p>
      )}

      {result && <Result result={result} />}
    </div>
  );
}

function Result({ result }: { result: AskResponse }) {
  if (result.outcome !== "answered") return <Empty result={result} />;

  return (
    <section className="mt-6 rounded border border-rule bg-card p-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule pb-2">
        <h2 className="font-display text-[20px]">Answer</h2>
        <span className="font-mono text-[13px] text-brass">
          as of {result.as_of} · {result.mode}
          {result.grounded_without_model && " · no model call"}
        </span>
      </header>

      <p className="mt-3 max-w-2xl whitespace-pre-wrap text-[15px] leading-[1.55]">
        {result.answer}
      </p>

      <h3 className="mt-5 border-t border-rule pt-3 text-[13px] font-medium text-brass">
        Grounded in {result.citations.length} retrieved passage
        {result.citations.length === 1 ? "" : "s"}
      </h3>
      <ul className="mt-2 space-y-2">
        {result.citations.map((citation) => (
          <Source key={`${citation.doc_id}-${citation.content.slice(0, 24)}`} citation={citation} />
        ))}
      </ul>
    </section>
  );
}

function Source({ citation }: { citation: Citation }) {
  return (
    <li className="rounded border border-rule bg-white p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[13px]">
          [{citation.doc_id}, effective {citation.effective_from}]
        </span>
        <span className="font-mono text-[13px] text-brass">
          {citation.similarity.toFixed(3)}
        </span>
      </div>
      <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[13px] leading-[1.5] text-ink/80">
        {citation.content}
      </p>
    </li>
  );
}

/**
 * The two empty outcomes, deliberately given different words.
 *
 * `none_in_force` is a finding: the corpus covers this supplier and no document
 * covered that date. `not_found` is an absence. Showing "no results" for both
 * would throw away the distinction the schema, the loader and the retriever all
 * exist to preserve.
 */
function Empty({ result }: { result: AskResponse }) {
  const gap = result.outcome === "none_in_force";
  return (
    <section className="mt-6 rounded border border-rule bg-card p-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule pb-2">
        <h2 className="font-display text-[20px] text-brass">
          {gap ? "No document in force" : "Not found"}
        </h2>
        <span className="font-mono text-[13px] text-brass">
          as of {result.as_of} · no model call
        </span>
      </header>
      <p className="mt-3 max-w-2xl text-[15px] leading-[1.55]">
        {gap ? (
          <>
            Documents exist for this scope, and <strong>none of them covered
            this date</strong>. That is not the same as having nothing on file —
            and it is not a search that failed.
          </>
        ) : (
          <>
            Nothing is held for this scope at all. Distinct from a date falling
            in a gap between documents.
          </>
        )}
      </p>
      <p className="mt-3 border-t border-rule pt-3 text-[13px] text-brass">
        No model was called: there is nothing to ground an answer in, and asking
        anyway would invite an answer from general knowledge.
      </p>
    </section>
  );
}
