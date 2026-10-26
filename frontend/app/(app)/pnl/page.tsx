"use client";

import { PageHeader } from "@/components/layout/page-header";
import { BacktestPnlView } from "@/components/pnl/backtest-pnl";

const BLURB =
  "Simulated P&L of your backtests after brokerage, slippage and taxes.";

export default function PnlPage() {
  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <PageHeader
        title="Profit & Loss"
        description={`${BLURB} Pick a day or a date range.`}
      />
      <BacktestPnlView />
    </main>
  );
}
