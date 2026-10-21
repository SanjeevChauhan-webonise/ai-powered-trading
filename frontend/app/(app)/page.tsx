"use client";

import Link from "next/link";

import { ErrorNote, PageHeader, PnlText } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { dateTime, shortDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

const RUN_TONE: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  running: "bg-primary/10 text-primary",
  queued: "bg-muted text-muted-foreground",
};

function Stat({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold">{children}</div>
        {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const { data, error } = useLoad(() =>
    Promise.all([api.datasets(), api.backtests(), api.runs(), api.health()]),
  );
  const [datasets, backtests, runs, health] = data ?? [[], [], [], null];
  const done = backtests.filter((b) => b.status === "completed");
  const totalPnl = done.reduce((s, b) => s + (b.total_pnl ?? 0), 0);
  const winners = done.filter((b) => (b.total_pnl ?? 0) > 0).length;

  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <PageHeader
        title="Dashboard"
        description="Everything at a glance: data, AI runs and backtest results. All results are simulated."
        action={
          <div className="flex gap-2">
            <Link href="/backtest/new" className={buttonVariants({ variant: "outline", size: "lg" })}>
              New backtest
            </Link>
            <Link href="/strategy-desk" className={buttonVariants({ size: "lg" })}>
              Open Strategy Desk
            </Link>
          </div>
        }
      />
      {error && <ErrorNote message={error} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Datasets" hint={datasets[0] ? `Latest: ${datasets[0].name}` : "Load data to begin"}>
          {datasets.length}
        </Stat>
        <Stat label="AI runs" hint={`${runs.filter((r) => r.status === "completed").length} completed`}>
          {runs.length}
        </Stat>
        <Stat label="Backtests" hint={done.length ? `${winners} of ${done.length} profitable` : undefined}>
          {backtests.length}
        </Stat>
        <Stat label="Backtest P&L (sum)" hint="Simulated, across all runs">
          <PnlText value={done.length ? totalPnl : null} />
        </Stat>
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader>
          <CardTitle className="text-base">Recent AI runs</CardTitle>
          <CardAction><Link href="/strategy-desk" className="text-xs text-primary hover:underline">New</Link></CardAction>
        </CardHeader>
          <CardContent>
            {runs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No runs yet. Ask the agents on the Strategy Desk.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow><TableHead>Idea</TableHead><TableHead>Status</TableHead><TableHead>When</TableHead></TableRow>
                </TableHeader>
                <TableBody>
                  {runs.slice(0, 8).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="max-w-xs truncate">
                        <Link href={`/strategy-desk?run=${r.id}`} className="hover:underline">
                          {r.idea ?? "(template run)"}
                        </Link>
                      </TableCell>
                      <TableCell><Badge className={RUN_TONE[r.status] ?? ""}>{r.status}</Badge></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{dateTime(r.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
          <CardTitle className="text-base">Recent backtests</CardTitle>
          <CardAction><Link href="/backtest" className="text-xs text-primary hover:underline">All</Link></CardAction>
        </CardHeader>
          <CardContent>
            {backtests.length === 0 ? (
              <p className="text-sm text-muted-foreground">No backtests yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow><TableHead>Strategy</TableHead><TableHead className="text-right">Net P&amp;L</TableHead><TableHead className="text-right">Trades</TableHead></TableRow>
                </TableHeader>
                <TableBody>
                  {backtests.slice(0, 8).map((b) => (
                    <TableRow key={b.id}>
                      <TableCell><Link href={`/results/${b.id}`} className="hover:underline">{b.strategy_name}</Link></TableCell>
                      <TableCell className="text-right"><PnlText value={b.total_pnl} /></TableCell>
                      <TableCell className="text-right font-mono">{b.num_trades ?? "–"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Datasets</CardTitle>
          <CardAction><span className="text-xs text-muted-foreground">API {health?.status ?? "…"}</span></CardAction>
        </CardHeader>
        <CardContent>
          {datasets.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No datasets. Load NIFTY / BANKNIFTY history with the Upstox export scripts, or create a synthetic one
              from New backtest.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead><TableHead>Underlying</TableHead><TableHead>Range</TableHead>
                  <TableHead className="text-right">Candle</TableHead>
                  <TableHead className="text-right">Underlying rows</TableHead><TableHead className="text-right">Option rows</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datasets.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell>{d.name}</TableCell>
                    <TableCell>{d.underlying}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {d.start_date ? `${shortDate(d.start_date)} – ${shortDate(d.end_date ?? d.start_date)}` : "–"}
                    </TableCell>
                    <TableCell className="text-right font-mono">{d.timeframe_minutes ? `${d.timeframe_minutes}m` : "–"}</TableCell>
                    <TableCell className="text-right font-mono">{d.underlying_rows.toLocaleString("en-IN")}</TableCell>
                    <TableCell className="text-right font-mono">{d.options_rows.toLocaleString("en-IN")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
