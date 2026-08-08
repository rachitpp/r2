"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  STORES,
  ask,
  listDemoQuestions,
  type DemoQuestion,
  type QueryResponse,
} from "@/lib/api";

export default function QueryView() {
  const [catalogue, setCatalogue] = useState<DemoQuestion[]>([]);
  const [selected, setSelected] = useState<DemoQuestion | null>(null);
  const [storeId, setStoreId] = useState<number | "">("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listDemoQuestions()
      .then(setCatalogue)
      .catch((e: Error) => setError(e.message));
  }, []);

  // The API refuses to guess a store rather than answer the wrong shop. A UI
  // that pre-filled one would reintroduce exactly that, one layer up — so the
  // control starts empty and the button stays disabled until it is chosen.
  const needsStore = selected?.requires_store === true;
  const ready = selected !== null && (!needsStore || storeId !== "");

  async function submit() {
    if (!selected || !ready) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await ask({
          question: selected.question,
          role: needsStore ? "clerk" : "owner",
          store_id: needsStore ? Number(storeId) : null,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-5 py-10">
      <header className="mb-8">
        <h1 className="font-display text-[28px] leading-[1.15] tracking-tight">
          Ask about the shop
        </h1>
        <p className="mt-1 text-[13px] text-brass">
          demo mode · answered from a fixed set, with no model call
        </p>
      </header>

      <section className="rounded border border-rule bg-card p-4">
        <label htmlFor="question" className="block text-[13px] font-medium">
          Question
        </label>
        <select
          id="question"
          className="mt-1 w-full rounded border border-rule bg-white px-3 py-2 text-[15px]"
          value={selected?.question ?? ""}
          onChange={(e) => {
            setSelected(catalogue.find((q) => q.question === e.target.value) ?? null);
            setStoreId("");
            setResult(null);
          }}
        >
          <option value="">Choose a question…</option>
          {catalogue.map((q) => (
            <option key={q.question} value={q.question}>
              {q.question}
              {q.expect === "refusal" ? "  — will decline" : ""}
              {q.requires_store ? "  — needs a store" : ""}
            </option>
          ))}
        </select>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="store" className="block text-[13px] font-medium">
              Store
            </label>
            <select
              id="store"
              disabled={!needsStore}
              className="mt-1 rounded border border-rule bg-white px-3 py-2 text-[15px] disabled:opacity-40"
              value={storeId}
              onChange={(e) => setStoreId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">{needsStore ? "Choose a store…" : "not needed"}</option>
              {STORES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={submit}
            disabled={!ready || busy}
            className="rounded bg-indigo px-4 py-2 text-[15px] font-medium text-white disabled:opacity-40"
          >
            {busy ? "Asking…" : "Ask"}
          </button>
          {needsStore && storeId === "" && (
            <p className="text-[13px] text-brass">
              This question is about one store. Choose which.
            </p>
          )}
        </div>
      </section>

      {error && (
        <p role="alert" className="mt-6 rounded border border-oxide/40 bg-card p-4 text-[15px] text-oxide">
          {error}
        </p>
      )}

      {result?.refusal && <Refusal response={result} />}
      {result?.answer && <Result response={result} />}
    </main>
  );
}

/** A refusal is a correct answer of a different kind. It renders in `ink`,
 *  never `oxide` — styling it red would teach a reader it is a malfunction to
 *  work around, when it is the system declining to fabricate. */
function Refusal({ response }: { response: QueryResponse }) {
  return (
    <section className="mt-6 rounded border border-rule bg-card p-5">
      <h2 className="font-display text-[20px]">This can&apos;t be answered from the data.</h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-[1.55]">
        {response.refusal?.replace(/^--\s*INSUFFICIENT SCHEMA:\s*/, "")}
      </p>
      <p className="mt-4 border-t border-rule pt-3 text-center font-mono text-[13px]">
        no query was run
      </p>
    </section>
  );
}

function Result({ response }: { response: QueryResponse }) {
  const a = response.answer!;
  return (
    <div className="mt-6 grid gap-5 md:grid-cols-2">
      <section className="rounded border border-rule bg-card p-4">
        <h2 className="font-display text-[20px]">Answer</h2>
        {/* One row, both states, same position. A complete answer needs no
            attention and reads in ink; a truncated one carries the API's own
            notice in brass. It never disappears and never moves. */}
        <p className={`mt-1 font-mono text-[13px] tnum ${a.truncated ? "text-brass" : ""}`}>
          {a.truncated ? a.notice : `${a.row_count} rows`}
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-rule text-left">
                {a.columns.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono tnum">
              {a.rows.map((row, i) => (
                <tr key={i} className="border-b border-rule/50">
                  {row.map((cell, j) => (
                    <td key={j} className="py-1 pr-3">{cell === null ? "—" : String(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Never behind a disclosure. A "show SQL" toggle would make the query a
          debug affordance and concede that the answer is the product. */}
      <section className="rounded border border-rule bg-card p-4">
        <h2 className="font-display text-[20px]">The query that produced it</h2>
        <pre className="mt-3 overflow-x-auto font-mono text-[13px] leading-[1.4]">
          {response.sql}
        </pre>
      </section>
    </div>
  );
}
