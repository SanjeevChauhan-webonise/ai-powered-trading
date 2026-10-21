"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ErrorNote, PageHeader, PnlText } from "@/components/layout/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type BacktestSummary } from "@/lib/api";
import { dateTime, money, shortDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

const GREEN = "#16a34a";
const RED = "#dc2626";
const GRID = "rgba(128,128,128,0.25)";

function byStrategy(runs: BacktestSummary[]) {
  const m = new Map<string, { runs: number; pnl: number; trades: number; wins: number }>();
  for (const r of runs) {
    const g = m.get(r.strategy_name) ?? { runs: 0, pnl: 0, trades: 0, wins: 0 };
    g.runs += 1;
    g.pnl += r.total_pnl ?? 0;
    g.trades += r.num_trades ?? 0;
    g.wins += (r.total_pnl ?? 0) > 0 ? 1 : 0;
    m.set(r.strategy_name, g);
  }
  return [...m.entries()].map(([name, g]) => ({ name, ...g })).sort((a, b) => b.pnl - a.pnl);
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold">{children}</div>
      </CardContent>
    </Card>
  );
}

export default function PnlPage() {
  const { data, error } = useLoad(api.backtests);
  const runs = (data ?? []).filter((r) => r.status === "completed" && r.total_pnl != null);
  const chrono = [...runs].reverse();
  const total = runs.reduce((s, r) => s + (r.total_pnl ?? 0), 0);
  const best = runs.reduce<BacktestSummary | null>((b, r) => (!b || (r.total_pnl ?? 0) > (b.total_pnl ?? 0) ? r : b), null);
  const worst = runs.reduce<BacktestSummary | null>((b, r) => (!b || (r.total_pnl ?? 0) < (b.total_pnl ?? 0) ? r : b), null);
  const wins = runs.filter((r) => (r.total_pnl ?? 0) > 0).length;
  const trades = runs.reduce((s, r) => s + (r.num_trades ?? 0), 0);
  const chart = chrono.map((r, i) => ({ n: i + 1, name: r.strategy_name, pnl: r.total_pnl ?? 0, at: r.created_at }));

  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <PageHeader
        title="Profit & Loss"
        description="Net P&L of your backtests after brokerage, slippage and taxes. Simulated on past data: no real or paper money is involved."
      />
      {error && <ErrorNote message={error} />}
      {!data && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
      {data && runs.length === 0 && (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          No completed backtests yet. <Link href="/backtest/new" className="text-primary hover:underline">Run one</Link> to see P&amp;L here.
        </CardContent></Card>
      )}

      {runs.length > 0 && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Total net P&L"><PnlText value={total} /></Stat>
            <Stat label="Profitable runs"><span className="font-mono">{wins} / {runs.length}</span></Stat>
            <Stat label="Best run"><PnlText value={best?.total_pnl} /></Stat>
            <Stat label="Worst run"><PnlText value={worst?.total_pnl} /></Stat>
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">Net P&amp;L per backtest ({trades} trades in total)</CardTitle></CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="n" fontSize={11} tickFormatter={(n) => `#${n}`} />
                  <YAxis tickFormatter={money} width={80} fontSize={11} />
                  <Tooltip
                    labelFormatter={(_, p) => (p[0] ? `${p[0].payload.name} · ${dateTime(p[0].payload.at)}` : "")}
                    formatter={(v) => [money(Number(v)), "Net P&L"]}
                  />
                  <ReferenceLine y={0} stroke={GRID} />
                  <Bar dataKey="pnl" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                    {chart.map((c) => <Cell key={c.n} fill={c.pnl >= 0 ? GREEN : RED} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="grid items-start gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">By strategy</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Strategy</TableHead><TableHead className="text-right">Runs</TableHead>
                    <TableHead className="text-right">Trades</TableHead><TableHead className="text-right">Net P&amp;L</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {byStrategy(runs).map((g) => (
                      <TableRow key={g.name}>
                        <TableCell>{g.name}</TableCell>
                        <TableCell className="text-right font-mono">{g.runs}</TableCell>
                        <TableCell className="text-right font-mono">{g.trades}</TableCell>
                        <TableCell className="text-right"><PnlText value={g.pnl} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">All runs</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Strategy</TableHead><TableHead>Period</TableHead>
                    <TableHead className="text-right">Net P&amp;L</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {runs.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell><Link href={`/results/${r.id}`} className="hover:underline">{r.strategy_name}</Link></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {r.start && r.end ? `${shortDate(r.start)} – ${shortDate(r.end)}` : "full dataset"}
                        </TableCell>
                        <TableCell className="text-right"><PnlText value={r.total_pnl} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </main>
  );
}
