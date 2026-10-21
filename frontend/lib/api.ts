import type { components } from "./api-types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type S = components["schemas"];
export type Dataset = S["DatasetOut"];
export type Template = S["TemplateOut"];
export type BacktestRequest = S["BacktestRequest"];
export type BacktestRun = S["BacktestRunOut"];
export type BacktestResult = S["BacktestResult"];
export type BacktestTrade = S["BacktestTrade"];
export type BacktestMetrics = S["BacktestMetrics"];
export type Health = S["HealthResponse"];

export class ApiError extends Error {}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
      .join("; ");
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(`Cannot reach the backend at ${API_URL}`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(formatDetail(body.detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  datasets: () => request<Dataset[]>("/datasets"),
  createSynthetic: () =>
    request<Dataset>("/datasets/synthetic", { method: "POST", body: "{}" }),
  templates: () => request<Template[]>("/strategies/templates"),
  runBacktest: (body: BacktestRequest) =>
    request<BacktestRun>("/backtests", { method: "POST", body: JSON.stringify(body) }),
  getBacktest: (id: string) => request<BacktestRun>(`/backtests/${id}`),
};
