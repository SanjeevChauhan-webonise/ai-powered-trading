"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestResult } from "@/lib/api";
import { dateTime, money, shortDate } from "@/lib/format";

const BLUE = "#2563eb";
const GREEN = "#16a34a";
const RED = "#dc2626";
const GRID = "rgba(128,128,128,0.25)";

function ChartCard({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          {children as React.ReactElement}
        </ResponsiveContainer>
      </CardContent>
      {note && (
        <p className="px-4 pb-3 text-xs text-muted-foreground">{note}</p>
      )}
    </Card>
  );
}

function drawdownSeries(
  equity: { t: string; equity: number }[],
  capital: number,
) {
  const out: { t: string; dd: number }[] = [];
  let peak = capital;
  for (const p of equity) {
    peak = Math.max(peak, p.equity);
    out.push({ t: p.t, dd: -((peak - p.equity) / peak) * 100 });
  }
  return out;
}

export function ResultCharts({ result }: { result: BacktestResult }) {
  const equity = result.equity_curve.map((p) => ({
    t: p.timestamp,
    equity: p.equity,
  }));
  const drawdown = drawdownSeries(equity, result.capital);
  const daily = result.metrics.daily_pnl.map((d) => ({
    d: d.date,
    pnl: d.pnl,
  }));

  if (equity.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No trades, so there is nothing to chart.
      </p>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard
        title="Equity curve (realised, per trade)"
        note="Starting capital plus the Net P&L of every closed trade. A rising line is profit; the dotted line is the starting capital."
      >
        <LineChart data={equity}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={shortDate}
            minTickGap={40}
            fontSize={11}
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={money}
            width={80}
            fontSize={11}
          />
          <Tooltip
            labelFormatter={(l) => dateTime(String(l))}
            formatter={(v) => [money(Number(v)), "Equity"]}
          />
          <ReferenceLine
            y={result.capital}
            stroke={GRID}
            strokeDasharray="4 4"
          />
          <Line
            isAnimationActive={false}
            type="stepAfter"
            dataKey="equity"
            stroke={BLUE}
            dot={false}
            strokeWidth={2}
          />
        </LineChart>
      </ChartCard>
      <ChartCard
        title="Drawdown (% from peak equity)"
        note="How far equity fell below its previous peak. The deeper the dip, the worse the losing streak."
      >
        <AreaChart data={drawdown}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={shortDate}
            minTickGap={40}
            fontSize={11}
          />
          <YAxis
            tickFormatter={(v) => `${Number(v).toFixed(1)}%`}
            width={60}
            fontSize={11}
          />
          <Tooltip
            labelFormatter={(l) => dateTime(String(l))}
            formatter={(v) => [`${Number(v).toFixed(2)}%`, "Drawdown"]}
          />
          <Area
            isAnimationActive={false}
            type="stepAfter"
            dataKey="dd"
            stroke={RED}
            fill={RED}
            fillOpacity={0.25}
          />
        </AreaChart>
      </ChartCard>
      <div className="lg:col-span-2">
        <ChartCard
          title="Daily P&L"
          note="Net P&L of each day's trades. Green is a profit day, red is a loss day."
        >
          <BarChart data={daily}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="d"
              tickFormatter={shortDate}
              minTickGap={20}
              fontSize={11}
            />
            <YAxis tickFormatter={money} width={80} fontSize={11} />
            <Tooltip
              labelFormatter={(l) => shortDate(String(l))}
              formatter={(v) => [money(Number(v)), "P&L"]}
            />
            <ReferenceLine y={0} stroke={GRID} />
            <Bar isAnimationActive={false} dataKey="pnl">
              {daily.map((d) => (
                <Cell key={d.d} fill={d.pnl >= 0 ? GREEN : RED} />
              ))}
            </Bar>
          </BarChart>
        </ChartCard>
      </div>
    </div>
  );
}
