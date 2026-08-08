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
  refusal: string | null;
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
