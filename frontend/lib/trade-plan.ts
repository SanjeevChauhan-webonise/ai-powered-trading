import type { Run, RunStep } from "./api";

/** Shape of `steps[risk].output.trade_plan` built by the backend (app/agents/trade_plan.py). */
export interface TradePlan {
  underlying: string;
  expiry_date: string | null;
  expiry_type: string;
  strategy: string;
  bullish_signal_action: string | null;
  bearish_signal_action: string | null;
  strike: { mode: string; offset: number; premium: number | null };
  entry_window: string;
  square_off: string;
  max_trades_per_day: number | null;
  lots: number;
  quantity: number | null;
  entry_premium_estimate: number | null;
  stop_loss_pct: number | null;
  target_pct: number | null;
  trailing_sl_pct: number | null;
  max_loss_per_trade: number | null;
  target_profit_per_trade: number | null;
  when_to_trade: string;
  reasons: string[];
  assumptions: string[];
  explanation: string;
  verification: { verdict: string | null; summary: string | null };
  backtest: Record<string, number | null>;
  notes: string[];
}

export const STEP_LABELS: Record<string, string> = {
  research: "Research agent",
  strategy: "Strategy agent",
  verify: "Verify agent",
  backtest: "Backtest agent",
  risk: "Risk review agent",
};

export const stepOf = (run: Run | null, name: string): RunStep | undefined =>
  run?.steps.find((s) => s.name === name);

export const tradePlanOf = (run: Run | null): TradePlan | null =>
  (stepOf(run, "risk")?.output?.trade_plan as TradePlan | undefined) ?? null;

export function stepSeconds(step: RunStep): number | null {
  if (!step.started_at || !step.finished_at) return null;
  return (new Date(step.finished_at).getTime() - new Date(step.started_at).getTime()) / 1000;
}
