"use client";

import { useEffect, useState } from "react";
import Documents from "./documents";
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
  const [question, setQuestion] = useState("");
  const [storeId, setStoreId] = useState<number | "">("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [beat, setBeat] = useState<"sql" | "docs">("sql");

  useEffect(() => {
    listDemoQuestions()
      .then(setCatalogue)
      .catch((e: Error) => setError(e.message));
  }, []);

  // The question is typed, with the catalogue offered as suggestions. One
  // control for both modes on purpose: `DEMO_MODE` is API-side only
  // (docs/CONVENTIONS.md), so this must not become two inputs behind a flag.
  // A question the API cannot take is refused *by the API*, with its own
  // reason, which is the honest way for the boundary to say no.
  const listed = catalogue.find((q) => q.question === question) ?? null;

  // The API refuses to guess a store rather than answer the wrong shop. A UI
  // that pre-filled one would reintroduce exactly that, one layer up — so the
  // control starts empty, and for a question known to need a store the button
  // stays disabled until it is chosen.
  const needsStore = listed?.requires_store === true;
  const scoped = storeId !== "";
  const ready = question.trim() !== "" && (!needsStore || scoped);

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await ask({
          question,
          // Choosing a store asks as a clerk restricted to it; leaving it empty
          // asks chain-wide. The scope reaches the model before it writes any
          // SQL — it is never applied to the rows afterwards.
          role: scoped ? "clerk" : "owner",
          store_id: scoped ? Number(storeId) : null,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Two beats, two shapes of evidence. Beat 1 shows the SQL it ran; beat 2
  // shows the passages it retrieved. Tabs rather than one merged view, because
  // the thing each demonstrates is different and a combined form would blur
  // both — "answer beside its query" and "same question, moved through time".
  return (
    <main className="mx-auto max-w-6xl px-5 py-10">
      <header className="mb-6">
        <h1 className="font-display text-[28px] leading-[1.15] tracking-tight">
          {beat === "sql" ? "Ask about the shop" : "Ask about the documents"}
        </h1>
        <p className="mt-1 text-[13px] text-brass">
          {beat === "sql"
            ? "the answer, beside the query that produced it"
            : "the same question, moved through time — the date is the variable"}
        </p>
      </header>

      <nav className="mb-6 flex gap-1 border-b border-rule" aria-label="Demo beats">
        {(
          [
            ["sql", "Query"],
            ["docs", "Documents"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setBeat(key)}
            aria-current={beat === key ? "page" : undefined}
            className={
              "-mb-px border-b-2 px-3 py-2 text-[15px] " +
              (beat === key
                ? "border-indigo font-medium text-indigo"
                : "border-transparent text-brass")
            }
          >
            {label}
          </button>
        ))}
      </nav>

      {beat === "docs" && <Documents />}
      {beat === "sql" && (
        <>

      <section className="rounded border border-rule bg-card p-4">
        <label htmlFor="question" className="block text-[13px] font-medium">
          Question
        </label>
        {/* Typed, with the catalogue as suggestions. The list is what the API
            can answer with no model call; anything else needs the live path,
            and the API says which rather than this input guessing. */}
        <input
          id="question"
          list="catalogue"
          autoComplete="off"
          placeholder="Ask about the shop…"
          className="mt-1 w-full rounded border border-rule bg-white px-3 py-2 text-[15px]"
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value);
            setResult(null);
          }}
        />
        <datalist id="catalogue">
          {catalogue.map((q) => (
            <option key={q.question} value={q.question}>
              {q.expect === "refusal" ? "will decline" : ""}
              {q.requires_store ? " needs a store" : ""}
            </option>
          ))}
        </datalist>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="store" className="block text-[13px] font-medium">
              Store
            </label>
            <select
              id="store"
              className="mt-1 rounded border border-rule bg-white px-3 py-2 text-[15px]"
              value={storeId}
              onChange={(e) => setStoreId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">{needsStore ? "Choose a store…" : "all stores"}</option>
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
          <p className="text-[13px] text-brass">
            {needsStore && !scoped
              ? "This question is about one store. Choose which."
              : scoped
                ? "Asked as a clerk, restricted to that store."
                : "Asked across every store."}
          </p>
        </div>
      </section>

      {error && (
        <p role="alert" className="mt-6 rounded border border-oxide/40 bg-card p-4 text-[15px] text-oxide">
          {error}
        </p>
      )}

      {result?.refusal && <Refusal response={result} />}
      {result?.error && <Failure response={result} />}
      {result?.answer && <Result response={result} />}
        </>
      )}
    </main>
  );
}

/** What produced this answer, stated per answer rather than per page. The page
 *  cannot know the mode before it asks — `DEMO_MODE` is API-side — and after it
 *  asks, the response says. */
function Provenance({ response }: { response: QueryResponse }) {
  return (
    <p className="mt-4 border-t border-rule pt-3 text-center font-mono text-[13px] text-brass">
      {response.mode === "demo"
        ? "answered from the fixed set · no model call"
        : "SQL written by the model · generated fresh, may differ next time"}
    </p>
  );
}

/** A refusal is a correct answer of a different kind. It renders in `ink`,
 *  never `oxide` — styling it red would teach a reader it is a malfunction to
 *  work around, when it is the system declining to fabricate. */
function Refusal({ response }: { response: QueryResponse }) {
  // Two sentinels, and they are not the same claim: one says the database
  // cannot answer this for anyone, the other that it can but not for this user.
  const outOfScope = /^--\s*OUT OF SCOPE:/.test(response.refusal ?? "");
  return (
    <section className="mt-6 rounded border border-rule bg-card p-5">
      <h2 className="font-display text-[20px]">
        {outOfScope
          ? "This isn’t yours to see."
          : "This can’t be answered from the data."}
      </h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-[1.55]">
        {response.refusal?.replace(
          /^--\s*(INSUFFICIENT SCHEMA|OUT OF SCOPE):\s*/,
          "",
        )}
      </p>
      <p className="mt-4 border-t border-rule pt-3 text-center font-mono text-[13px] text-brass">
        no query was run ·{" "}
        {response.mode === "demo" ? "answered from the fixed set" : "the model declined"}
      </p>
    </section>
  );
}

/** The generated query was refused by the guard or rejected by Postgres. This
 *  one *is* a fault, so it carries oxide — the distinction from a refusal is
 *  the whole point, and it is why `error` is a separate field. The query that
 *  failed is shown: a failure you cannot read teaches nothing. */
function Failure({ response }: { response: QueryResponse }) {
  return (
    <section className="mt-6 rounded border border-oxide/40 bg-card p-5">
      <h2 className="font-display text-[20px] text-oxide">
        The query didn’t run.
      </h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-[1.55]">{response.error}</p>
      {response.generated_sql && (
        <pre className="mt-3 overflow-x-auto border-t border-rule pt-3 font-mono text-[13px] leading-[1.4]">
          {response.generated_sql}
        </pre>
      )}
      <Provenance response={response} />
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
        <Provenance response={response} />
      </section>
    </div>
  );
}
