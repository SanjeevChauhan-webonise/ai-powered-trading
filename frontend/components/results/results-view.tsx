"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { MetricCards } from "@/components/results/metric-cards";
import { ResultCharts } from "@/components/results/charts";
import { StrategyExplainer } from "@/components/results/explain";
import { VerificationBanner } from "@/components/results/verification";
import { TradeTable } from "@/components/results/trade-table";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type BacktestRun } from "@/lib/api";
import { dateTime } from "@/lib/format";

export function ResultsView() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getBacktest(id)
      .then(setRun)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  if (error)
    return <main className="mx-auto max-w-6xl p-6 text-red-600">{error}</main>;
  if (!run) return <main className="mx-auto max-w-6xl p-6">Loading…</main>;
  if (!run.result) {
    return (
      <main className="mx-auto max-w-6xl p-6 text-red-600">
        Run failed: {run.error}
      </main>
    );
  }
  const { result } = run;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{run.strategy_name}</h1>
          <p className="text-sm text-muted-foreground">
            {run.start ?? "dataset start"} → {run.end ?? "dataset end"} ·
            capital ₹{run.capital.toLocaleString("en-IN")} · lot size{" "}
            {result.lot_size} (NSE revises it by expiry; each trade shows its
            own Qty) · run {dateTime(run.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href={`/backtest/new?from=${run.id}`}
            className={buttonVariants({ variant: "outline" })}
          >
            Edit &amp; re-run
          </Link>
          <Link
            href="/backtest/new"
            className={buttonVariants({ variant: "outline" })}
          >
            New backtest
          </Link>
        </div>
      </div>

      <MetricCards m={result.metrics} />
      <ResultCharts result={result} />
      <StrategyExplainer run={run} />
      <VerificationBanner result={result} />
      <TradeTable trades={result.trades} />

      {result.events.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              Skipped events ({result.events.length}
              {result.events_truncated ? "+" : ""})
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-48 space-y-1 overflow-auto text-xs">
            {result.events.map((e, i) => (
              <div key={i}>
                <span className="text-muted-foreground">
                  {dateTime(e.timestamp)}
                </span>{" "}
                {e.kind}: {e.message}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>AI research and risk review</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          For a strategy built by the AI agents, the research, verification and
          risk review are on its Strategy Desk page: open the run from the
          Dashboard (Recent AI runs). A backtest started from New backtest has
          no AI review.
        </CardContent>
      </Card>
    </main>
  );
}
