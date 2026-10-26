"use client";

import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { BacktestPnlView } from "@/components/pnl/backtest-pnl";
import { PaperPnlView } from "@/components/pnl/paper-pnl";
import { SHOW_PAPER_TRADING } from "@/lib/features";

const ALL_TABS = [
  {
    id: "paper",
    label: "Paper account",
    blurb:
      "Realised P&L of your closed paper trades, by the day they were closed.",
  },
  {
    id: "backtest",
    label: "Backtests",
    blurb:
      "Simulated P&L of your backtests after brokerage, slippage and taxes.",
  },
] as const;
const TABS = ALL_TABS.filter((t) => SHOW_PAPER_TRADING || t.id !== "paper");

export default function PnlPage() {
  const [tab, setTab] = useState<(typeof ALL_TABS)[number]["id"]>(
    SHOW_PAPER_TRADING ? "paper" : "backtest",
  );
  const current = TABS.find((t) => t.id === tab)!;
  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <PageHeader
        title="Profit & Loss"
        description={`${current.blurb} Pick a day or a date range.`}
      />
      <div className="inline-flex rounded-xl bg-muted p-1 text-sm font-medium">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-4 py-1.5 ${tab === t.id ? "bg-card shadow-sm" : "text-muted-foreground"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "paper" ? <PaperPnlView /> : <BacktestPnlView />}
    </main>
  );
}
