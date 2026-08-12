/**
 * The typed client. `api/` is the only boundary between the two apps
 * (CLAUDE.md), and these types mirror the FastAPI response models exactly —
 * if they drift, the drift shows up here rather than as `undefined` in a cell.
 */

export type DemoQuestion = {
  question: string;
  /** The caller must supply a store. The API refuses to pick one, because
   *  picking would answer the wrong shop without saying so — so the UI must
   *  not default either. */
  requires_store: boolean;
  /** "refusal" means this question demonstrates the system declining. It is
   *  offered deliberately rather than stumbled into. */
  expect: "answer" | "refusal";
};

export type Answer = {
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  total_row_count: number;
  truncated: boolean;
  notice: string | null;
};

export type QueryResponse = {
  mode: "demo" | "live";
  question: string;
  /** The SQL actually executed, wrapper and all. Null only when the honest
   *  answer was a refusal — and the UI says "no query was run" rather than
   *  dropping the panel. */
  sql: string | null;
  /** What the model wrote, before the guard's wrapper. Live mode only, and
   *  present even when that SQL was refused or failed — a query you cannot see
   *  is a query you cannot check. */
  generated_sql: string | null;
  /** The model declining. A correct answer of a different kind, so it renders
   *  in ink and never in oxide. */
  refusal: string | null;
  /** The generated query was refused by the guard or rejected by Postgres.
   *  Never merged with `refusal`: "the data cannot answer this" and "the model
   *  wrote a bad query" are different facts, and only the second is a fault. */
  error: string | null;
  answer: Answer | null;
};

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let detail = `request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    /* a non-JSON error body is still an error; keep the status message */
  }
  throw new ApiError(response.status, detail);
}

export async function listDemoQuestions(): Promise<DemoQuestion[]> {
  return unwrap<DemoQuestion[]>(await fetch("/api/demo/questions"));
}

export async function ask(input: {
  question: string;
  role?: "clerk" | "manager" | "owner";
  store_id?: number | null;
}): Promise<QueryResponse> {
  return unwrap<QueryResponse>(
    await fetch("/api/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        question: input.question,
        role: input.role ?? "owner",
        ...(input.store_id ? { store_id: input.store_id } : {}),
      }),
    }),
  );
}

export const STORES = [
  { id: 1, name: "Kothrud, Pune" },
  { id: 2, name: "Gangapur Road, Nashik" },
  { id: 3, name: "Dharampeth, Nagpur" },
] as const;

/* ── Demo beat 2: grounded document Q&A ───────────────────────────────────
 *
 * Retrieval is local and free, so it runs for real in BOTH modes. Only the
 * answer text differs — replayed in demo, generated live — which means the
 * citations below are genuinely what retrieval returned either way.
 */

export type DocQuestion = {
  question: string;
  /** Part of the key, not a filter. Demo answers are recorded per date, and
   *  there is no nearest-date fallback: serving a neighbouring date's answer
   *  would contradict the one property this beat demonstrates. */
  as_of: string;
  supplier_code: string | null;
  outcome: string;
};

export type Citation = {
  doc_id: string;
  doc_type: string;
  effective_from: string;
  effective_to: string | null;
  similarity: number;
  /** The chunk text. Shown, never hidden — the same reason `/query` returns
   *  the SQL it ran. An answer whose sources you cannot read is one you
   *  cannot check. */
  content: string;
};

export type AskResponse = {
  mode: "demo" | "live";
  question: string;
  as_of: string;
  /** "answered" | "none_in_force" | "not_found".
   *
   *  THE LAST TWO MUST NOT BE COLLAPSED IN THE UI. "No contract covered that
   *  month" and "we hold nothing for this supplier" are different answers to
   *  different questions, and telling them apart is what this beat is for. */
  outcome: string;
  answer: string | null;
  citations: Citation[];
  /** True when no model call was made — always true for the two empty
   *  outcomes, because there is nothing to ground an answer in. */
  grounded_without_model: boolean;
};

export async function listDocQuestions(): Promise<DocQuestion[]> {
  return unwrap<DocQuestion[]>(await fetch("/api/demo/document-questions"));
}

export async function askDocuments(input: {
  question: string;
  as_of: string;
  role?: "clerk" | "manager" | "owner";
  store_id?: number | null;
  supplier_code?: string | null;
  doc_types?: string[] | null;
}): Promise<AskResponse> {
  return unwrap<AskResponse>(
    await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        question: input.question,
        as_of: input.as_of,
        role: input.role ?? "owner",
        ...(input.store_id ? { store_id: input.store_id } : {}),
        ...(input.supplier_code ? { supplier_code: input.supplier_code } : {}),
        ...(input.doc_types ? { doc_types: input.doc_types } : {}),
      }),
    }),
  );
}
