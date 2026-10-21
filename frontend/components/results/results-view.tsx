"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { MetricCards } from "@/components/results/metric-cards";
import { ResultCharts } from "@/components/results/charts";
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

  if (error) return <main className="mx-auto max-w-6xl p-6 text-red-600">{error}</main>;
  if (!run) return <main className="mx-auto max-w-6xl p-6">Loading…</main>;
  if (!run.result) {
    return <main className="mx-auto max-w-6xl p-6 text-red-600">Run failed: {run.error}</main>;
  }
  const { result } = run;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{run.strategy_name}</h1>
          <p className="text-sm text-muted-foreground">
            {run.start ?? "dataset start"} → {run.end ?? "dataset end"} · capital ₹{run.capital.toLocaleString("en-IN")} · lot
            size {result.lot_size} · run {dateTime(run.created_at)}
          </p>
        </div>
        <Link href="/backtest/new" className={buttonVariants({ variant: "outline" })}>
          New backtest
        </Link>
      </div>

      <MetricCards m={result.metrics} />
      <ResultCharts result={result} />
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
                <span className="text-muted-foreground">{dateTime(e.timestamp)}</span> {e.kind}: {e.message}
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
          Coming in a later phase: the research and risk-review agents will summarise this run here.
        </CardContent>
      </Card>
    </main>
  );
}
