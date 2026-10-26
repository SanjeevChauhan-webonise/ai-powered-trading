import type { components } from "./api-types";
import { clearToken, getToken } from "./token";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type S = components["schemas"];
export type Dataset = S["DatasetOut"];
export type Template = S["TemplateOut"];
export type BacktestRequest = S["BacktestRequest"];
export type BacktestRun = S["BacktestRunOut"];
export type BacktestResult = S["BacktestResult"];
export type BacktestTrade = S["BacktestTrade"];
export type BacktestMetrics = S["BacktestMetrics"];
export type Health = S["HealthResponse"];
export type BacktestSummary = S["BacktestRunSummary"];
export type ParsedQuery = S["ParsedQuery"];
export type RunRequest = Omit<S["RunRequest-Input"], "dataset_id"> & {
  dataset_id?: string;
};
export type RunSummary = S["RunSummary"];
export type Run = S["RunOut"];
export type RunStep = S["StepRecord"];
export type ModelsResponse = S["ModelsResponse"];
export type ValidateResponse = S["ValidateResponse"];
export type KnowledgeDoc = S["DocumentInfo"];
export interface ChunkPage {
  source: string;
  total: number;
  offset: number;
  chunks: { id: string; heading: string; chunk_index: number; text: string }[];
}
export type KnowledgeChunk = S["RetrievedChunk"];
export type ExpiriesResponse = S["ExpiriesResponse"];
export type User = S["UserOut"];
export type TokenOut = S["TokenOut"];
export type Level = User["level"];
export type PaperAccount = S["AccountOut"];
export type PaperPosition = S["PositionOut"];
export type PaperOrder = S["OrderOut"];
export type PaperTrade = S["TradeOut"];
export type PaperChain = S["ChainOut"];
export type PaperAdvance = S["AdvanceOut"];
export type PaperFromPlan = S["FromPlanOut"];
export type PaperPnl = S["PnlOut"];
export type AskAnswer = S["AskAnswer"];

export class ApiError extends Error {}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map(
        (d: { loc?: unknown[]; msg?: string }) =>
          `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`,
      )
      .join("; ");
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const token = getToken();
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(`Cannot reach the backend at ${API_URL}`);
  }
  if (
    res.status === 401 &&
    !path.startsWith("/auth/login") &&
    !path.startsWith("/auth/register")
  ) {
    clearToken(); // the session ended or the token is invalid: back to the login page
    // a hard redirect on purpose: this helper has no router, and a dead session should reset the page state
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (typeof window !== "undefined" && window.location.pathname !== "/login")
      window.location.assign("/login");
    throw new ApiError("Please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(formatDetail(body.detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  login: (email: string, password: string) =>
    request<TokenOut>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (body: {
    email: string;
    name: string;
    password: string;
    level: Level;
  }) =>
    request<TokenOut>("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  me: () => request<User>("/auth/me"),
  updateMe: (body: { name?: string; level?: Level }) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(body) }),
  logout: () =>
    request<unknown>("/auth/logout", { method: "POST", body: "{}" }).catch(
      () => undefined,
    ),
  datasets: () => request<Dataset[]>("/datasets"),
  createSynthetic: () =>
    request<Dataset>("/datasets/synthetic", { method: "POST", body: "{}" }),
  templates: () => request<Template[]>("/strategies/templates"),
  validateSpec: (spec: unknown) =>
    request<ValidateResponse>("/strategies/validate", {
      method: "POST",
      body: JSON.stringify({ spec }),
    }),
  runBacktest: (body: BacktestRequest) =>
    request<BacktestRun>("/backtests", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getBacktest: (id: string) => request<BacktestRun>(`/backtests/${id}`),
  backtests: () => request<BacktestSummary[]>("/backtests"),
  parseQuery: (query: string, model?: string) =>
    request<ParsedQuery>("/runs/parse", {
      method: "POST",
      body: JSON.stringify({ query, model: model || null }),
    }),
  ask: (query: string, model?: string) =>
    request<AskAnswer>("/runs/ask", {
      method: "POST",
      body: JSON.stringify({ query, model: model || null }),
    }),
  createRun: (body: RunRequest) =>
    request<RunSummary>("/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getRun: (id: string) => request<Run>(`/runs/${id}`),
  runs: () => request<RunSummary[]>("/runs"),
  models: () => request<ModelsResponse>("/models"),
  paperAccount: () => request<PaperAccount>("/paper/account"),
  paperReset: (starting_balance?: number) =>
    request<PaperAccount>("/paper/account/reset", {
      method: "POST",
      body: JSON.stringify({ starting_balance: starting_balance ?? null }),
    }),
  paperStartClock: (dataset_id: string) =>
    request<PaperAccount>("/paper/clock/start", {
      method: "POST",
      body: JSON.stringify({ dataset_id }),
    }),
  paperAdvance: (candles: number) =>
    request<PaperAdvance>("/paper/clock/advance", {
      method: "POST",
      body: JSON.stringify({ candles }),
    }),
  paperExpiries: () =>
    request<{ dataset_id: string; clock_time: string; expiries: string[] }>(
      "/paper/expiries",
    ),
  paperChain: (expiry: string) =>
    request<PaperChain>(`/paper/chain?expiry=${expiry}`),
  paperPositions: () => request<PaperPosition[]>("/paper/positions"),
  paperOrders: (limit = 30) =>
    request<PaperOrder[]>(`/paper/orders?limit=${limit}`),
  paperTrades: (limit = 100, from?: string, to?: string) =>
    request<PaperTrade[]>(
      `/paper/trades?limit=${limit}${from ? `&date_from=${from}` : ""}${to ? `&date_to=${to}` : ""}`,
    ),
  paperPnl: (from?: string, to?: string) =>
    request<PaperPnl>(
      `/paper/pnl?${new URLSearchParams({ ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) })}`,
    ),
  paperBuy: (body: {
    expiry: string;
    strike: number;
    option_type: "CE" | "PE";
    lots: number;
    stop_pct?: number | null;
    target_pct?: number | null;
  }) =>
    request<PaperOrder>("/paper/orders", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  paperClose: (id: string, lots?: number) =>
    request<PaperTrade>(`/paper/positions/${id}/close`, {
      method: "POST",
      body: JSON.stringify({ lots: lots ?? null }),
    }),
  paperFromPlan: (run_id: string, option_type: "CE" | "PE") =>
    request<PaperFromPlan>("/paper/from-plan", {
      method: "POST",
      body: JSON.stringify({ run_id, option_type }),
    }),
  expiries: (underlying: string, count = 10) =>
    request<ExpiriesResponse>(
      `/expiries?underlying=${underlying}&count=${count}`,
    ),
  knowledgeDocs: () => request<KnowledgeDoc[]>("/knowledge/documents"),
  knowledgeChunks: (source: string, offset = 0, limit = 20) =>
    request<ChunkPage>(
      `/knowledge/chunks?${new URLSearchParams({ source, offset: String(offset), limit: String(limit) })}`,
    ),
  knowledgeSearch: (query: string, k = 5) =>
    request<KnowledgeChunk[]>("/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ query, k }),
    }),
  knowledgeIngest: () =>
    request<unknown>("/knowledge/ingest", { method: "POST", body: "{}" }),
  knowledgeUpload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    let res: Response;
    try {
      const token = getToken();
      res = await fetch(`${API_URL}/knowledge/upload`, {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(`Cannot reach the backend at ${API_URL}`);
    }
    if (!res.ok)
      throw new ApiError(
        formatDetail((await res.json().catch(() => ({}))).detail),
      );
    return res.json() as Promise<{ source: string; chunks: number }>;
  },
};
