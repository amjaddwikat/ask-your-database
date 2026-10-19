/**
 * Typed client for the ask-your-database API.
 * Mirrors backend/app/schemas.py; keep the two in sync.
 */

export type ResponseType = "general" | "blocked" | "clarification" | "analysis" | "plot" | "error";

export type Row = Record<string, unknown>;

export interface QueryData {
  sql: string;
  explanation: string;
  columns: string[];
  rows: Row[];
  row_count: number;
  truncated: boolean;
}

export interface ChartSpec {
  chart_type: "bar" | "line" | "pie" | "scatter";
  x: string;
  y: string;
  group_by: string | null;
  x_label: string;
  y_label: string;
  title: string;
}

export interface Chart {
  spec: ChartSpec;
  data: Row[];
}

export interface StepTrace {
  step: string;
  duration_ms: number;
  detail: string | null;
}

export interface ChatResponse {
  session_id: string;
  type: ResponseType;
  message: string;
  query: QueryData | null;
  chart: Chart | null;
  trace: StepTrace[];
}

export interface HistoryMessage {
  role: string;
  content: string;
  created_at: string;
}

interface ErrorEnvelope {
  error: { code: string; message: string; request_id: string | null };
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-API-Key": API_KEY, ...init.headers },
    });
  } catch {
    throw new ApiError(`Can't reach the API at ${BASE_URL}. Is the backend running?`, 0, "network_error");
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ErrorEnvelope | null;
    throw new ApiError(
      body?.error?.message ?? `Request failed with status ${res.status}`,
      res.status,
      body?.error?.code ?? "http_error",
      body?.error?.request_id ?? null,
    );
  }
  return (await res.json()) as T;
}

export function sendChat(message: string, sessionId?: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export function fetchHistory(sessionId: string): Promise<HistoryMessage[]> {
  return request<HistoryMessage[]>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`);
}
