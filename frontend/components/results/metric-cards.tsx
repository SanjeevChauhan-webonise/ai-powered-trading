import { Card, CardContent } from "@/components/ui/card";
import type { BacktestMetrics } from "@/lib/api";
import { money, num, pct } from "@/lib/format";

function Metric({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" }) {
  const color = tone === "pos" ? "text-green-600" : tone === "neg" ? "text-red-600" : "";
  return (
    <Card size="sm">
      <CardContent>
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

const tone = (n: number | null | undefined) => (n == null || n === 0 ? undefined : n > 0 ? "pos" : "neg");

export function MetricCards({ m }: { m: BacktestMetrics }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Metric label="Total P&L" value={money(m.total_pnl)} tone={tone(m.total_pnl)} />
      <Metric label="Win rate" value={pct(m.win_rate_pct)} />
      <Metric label="Profit factor" value={num(m.profit_factor)} />
      <Metric label="Sharpe" value={num(m.sharpe)} />
      <Metric label="Max drawdown" value={`${money(m.max_drawdown)} (${pct(m.max_drawdown_pct)})`} />
      <Metric label="Trades" value={String(m.num_trades)} />
      <Metric label="Expectancy / trade" value={money(m.expectancy)} tone={tone(m.expectancy)} />
      <Metric label="Total costs" value={money(m.total_costs)} />
      <Metric label="Avg win" value={money(m.avg_win)} />
      <Metric label="Avg loss" value={money(m.avg_loss)} />
      <Metric label="Best trade" value={money(m.best_trade)} />
      <Metric label="Worst trade" value={money(m.worst_trade)} />
    </div>
  );
}
