"use client";

import { useEffect, useState } from "react";
import { Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ErrorNote, PnlText } from "@/components/layout/page-header";
import { Trades } from "@/components/paper/tables";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type PaperPnl, type PaperTrade } from "@/lib/api";
import { ALL, dayLabel, type Range } from "@/lib/dates";
import { money, num } from "@/lib/format";

import { DateRange } from "./date-range";

const GREEN = "#16a34a";
const RED = "#dc2626";
const BLUE = "#2d3ed1";
const GRID = "rgba(128,128,128,0.25)";

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

function Groups({ title, rows }: { title: string; rows: PaperPnl["by_exit_reason"] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No trades in this period.</p>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead /><TableHead className="text-right">Trades</TableHead><TableHead className="text-right">Net P&amp;L</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((g) => (
                <TableRow key={g.key}>
                  <TableCell className="font-medium">{g.key}</TableCell>
                  <TableCell className="text-right font-mono">{g.trades}</TableCell>
                  <TableCell className="text-right"><PnlText value={g.net_pnl} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function PaperPnlView() {
  const [range, setRange] = useState<Range>(ALL);
  const [data, setData] = useState<PaperPnl | null>(null);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [bounds, setBounds] = useState<{ min: string | null; max: string | null }>({ min: null, max: null });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let on = true;
    Promise.all([api.paperPnl(range.from, range.to), api.paperTrades(500, range.from, range.to)])
      .then(([p, t]) => {
        if (!on) return;
        setError(null);
        setData(p);
        setTrades(t);
        setBounds({ min: p.available_from ?? null, max: p.available_to ?? null });
      })
      .catch((e: Error) => on && setError(e.message));
    return () => {
      on = false;
    };
  }, [range]);

  const s = data?.summary;
  return (
    <div className="space-y-5">
      <DateRange value={range} onChange={setRange} min={bounds.min} max={bounds.max} />
      {error && <ErrorNote message={error} />}
      {!data && !error && <p className="text-sm text-muted-foreground">Loading…</p>}

      {data && s && (
        <>
          <p className="text-xs text-muted-foreground">
            Realised P&amp;L of closed paper trades, by the (market-clock) day each trade was closed. Open positions are not
            included. Costs: brokerage and taxes.
          </p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Net P&L" hint={`gross ${money(s.gross_pnl)} − costs ${money(s.costs)}`}><PnlText value={s.net_pnl} /></Stat>
            <Stat label="Trades" hint={`${s.wins} won · ${s.losses} lost`}><span className="font-mono">{s.trades}</span></Stat>
            <Stat label="Win rate" hint={s.profit_factor != null ? `profit factor ${num(s.profit_factor)}` : "no losing trade"}>
              <span className="font-mono">{s.win_rate_pct != null ? `${num(s.win_rate_pct, 1)}%` : "–"}</span>
            </Stat>
            <Stat label="Max drawdown" hint="largest fall of the running P&L"><PnlText value={s.max_drawdown ? -s.max_drawdown : 0} /></Stat>
            <Stat label="Average win"><PnlText value={s.avg_win} /></Stat>
            <Stat label="Average loss"><PnlText value={s.avg_loss} /></Stat>
            <Stat label="Best trade"><PnlText value={s.best_trade} /></Stat>
            <Stat label="Worst trade"><PnlText value={s.worst_trade} /></Stat>
          </div>

          {data.daily.length === 0 ? (
            <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
              No closed trades in this period. Pick another range, or close a trade on the Paper Trading page.
            </CardContent></Card>
          ) : (
            <>
              <Card>
                <CardHeader><CardTitle className="text-base">Daily net P&amp;L and running total</CardTitle></CardHeader>
                <CardContent className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={data.daily}>
                      <CartesianGrid stroke={GRID} vertical={false} />
                      <XAxis dataKey="date" fontSize={11} tickFormatter={(d: string) => dayLabel(d).slice(0, 6)} />
                      <YAxis yAxisId="day" tickFormatter={money} width={80} fontSize={11} />
                      <YAxis yAxisId="cum" orientation="right" tickFormatter={money} width={80} fontSize={11} />
                      <Tooltip
                        labelFormatter={(d) => dayLabel(String(d))}
                        formatter={(v, name) => [money(Number(v)), name === "net_pnl" ? "Day" : "Running total"]}
                      />
                      <ReferenceLine yAxisId="day" y={0} stroke={GRID} />
                      <Bar yAxisId="day" dataKey="net_pnl" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                        {data.daily.map((d) => <Cell key={d.date} fill={d.net_pnl >= 0 ? GREEN : RED} />)}
                      </Bar>
                      <Line yAxisId="cum" dataKey="cumulative" stroke={BLUE} strokeWidth={2} dot={false} isAnimationActive={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <div className="grid items-start gap-5 xl:grid-cols-[1.2fr_1fr]">
                <Card>
                  <CardHeader><CardTitle className="text-base">By day (click a day to see only that day)</CardTitle></CardHeader>
                  <CardContent>
                    <div className="max-h-96 overflow-y-auto">
                      <Table>
                        <TableHeader><TableRow>
                          <TableHead>Date</TableHead><TableHead className="text-right">Trades</TableHead>
                          <TableHead className="text-right">Net P&amp;L</TableHead><TableHead className="text-right">Running total</TableHead>
                        </TableRow></TableHeader>
                        <TableBody>
                          {[...data.daily].reverse().map((d) => (
                            <TableRow key={d.date} className="cursor-pointer" onClick={() => setRange({ from: d.date, to: d.date })}>
                              <TableCell className="font-medium">{dayLabel(d.date)}</TableCell>
                              <TableCell className="text-right font-mono">{d.trades}</TableCell>
                              <TableCell className="text-right"><PnlText value={d.net_pnl} /></TableCell>
                              <TableCell className="text-right"><PnlText value={d.cumulative} /></TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
                <div className="space-y-5">
                  <Groups title="By exit reason" rows={data.by_exit_reason} />
                  <Groups title="By option type" rows={data.by_option_type} />
                </div>
              </div>
              <Trades rows={trades} />
            </>
          )}
        </>
      )}
    </div>
  );
}
