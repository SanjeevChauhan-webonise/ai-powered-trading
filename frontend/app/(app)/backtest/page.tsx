"use client";

import Link from "next/link";

import { ErrorNote, PageHeader, PnlText } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { dateTime, money, shortDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

export default function BacktestHistory() {
  const { data: runs, error } = useLoad(api.backtests);
  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <PageHeader
        title="Backtest"
        description="Every backtest, from the direct runner and from AI runs. Open one for charts and the full trade log."
        action={
          <Link href="/backtest/new" className={buttonVariants({ size: "lg" })}>
            New backtest
          </Link>
        }
      />
      {error && <ErrorNote message={error} />}
      <Card>
        <CardContent>
          {!runs && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
          {runs && runs.length === 0 && (
            <p className="text-sm text-muted-foreground">No backtests yet. Start one with New backtest.</p>
          )}
          {runs && runs.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Strategy</TableHead><TableHead>Period</TableHead>
                  <TableHead className="text-right">Capital</TableHead><TableHead>Status</TableHead>
                  <TableHead className="text-right">Net P&amp;L</TableHead><TableHead className="text-right">Trades</TableHead>
                  <TableHead>Run at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell><Link href={`/results/${r.id}`} className="font-medium hover:underline">{r.strategy_name}</Link></TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.start && r.end ? `${shortDate(r.start)} – ${shortDate(r.end)}` : "full dataset"}
                    </TableCell>
                    <TableCell className="text-right font-mono">{money(r.capital)}</TableCell>
                    <TableCell>
                      <Badge className={r.status === "completed" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}>{r.status}</Badge>
                    </TableCell>
                    <TableCell className="text-right"><PnlText value={r.total_pnl} /></TableCell>
                    <TableCell className="text-right font-mono">{r.num_trades ?? "–"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{dateTime(r.created_at)}</TableCell>
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
