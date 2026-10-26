"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestRun } from "@/lib/api";
import { money, num } from "@/lib/format";

const GREEN = "#16a34a";
const RED = "#dc2626";
const GRID = "rgba(128,128,128,0.25)";

type RawSpec = BacktestRun["spec"];
// The generated type marks every defaulted field optional; the API always sends them.
type Spec = Omit<RawSpec, "indicators" | "instrument" | "risk" | "costs"> & {
  indicators: NonNullable<RawSpec["indicators"]>;
  instrument: NonNullable<RawSpec["instrument"]> & {
    strike: NonNullable<NonNullable<RawSpec["instrument"]>["strike"]>;
  };
  risk: NonNullable<RawSpec["risk"]>;
  costs: NonNullable<RawSpec["costs"]> & {
    slippage: NonNullable<NonNullable<RawSpec["costs"]>["slippage"]>;
  };
};

/* ---- turn the declarative rules into a readable sentence ---------------------------------- */

const OPS: Record<string, string> = {
  crosses_above: "crosses above",
  crosses_below: "crosses below",
  ">": "is above",
  "<": "is below",
  between: "is between",
};

function operand(o: unknown, spec: Spec): string {
  const x = o as Record<string, unknown>;
  if ("indicator" in x) {
    const ind = spec.indicators.find((i) => i.id === x.indicator);
    const params = ind ? Object.values(ind.params ?? {}).join(",") : "";
    const base = ind
      ? `${ind.type.toUpperCase()}${params ? `(${params})` : ""}`
      : String(x.indicator);
    return x.output ? `${base}.${x.output}` : base;
  }
  if ("price" in x) return `${x.price} price`;
  if ("range" in x) return (x.range as number[]).join(" – ");
  return String(x.value);
}

function condition(c: unknown, spec: Spec): string[] {
  const x = c as Record<string, unknown>;
  if ("all" in x)
    return (x.all as unknown[])
      .flatMap((s) => condition(s, spec))
      .map((s, i) => (i === 0 ? s : `AND ${s}`));
  if ("any" in x)
    return [
      "Any one of: " +
        (x.any as unknown[]).flatMap((s) => condition(s, spec)).join("  OR  "),
    ];
  return [
    `${operand(x.left, spec)} ${OPS[String(x.op)] ?? String(x.op)} ${operand(x.right, spec)}`,
  ];
}

function Rules({ title, c, spec }: { title: string; c: unknown; spec: Spec }) {
  if (!c) return null;
  return (
    <div>
      <div className="font-medium">{title}</div>
      <ul className="list-disc pl-5 text-muted-foreground">
        {condition(c, spec).map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ul>
    </div>
  );
}

/* ---- the explainer card ------------------------------------------------------------------- */

export function StrategyExplainer({ run }: { run: BacktestRun }) {
  const spec = run.spec as Spec;
  const result = run.result!;
  const buy = spec.direction === "buy";
  const r = spec.risk;
  const t0 = result.trades[0];

  const gross = result.trades.reduce((s, t) => s + t.gross_pnl, 0);
  const brokerage = result.trades.reduce((s, t) => s + t.brokerage, 0);
  const taxes = result.trades.reduce((s, t) => s + t.taxes, 0);
  const slip = result.trades.reduce((s, t) => s + t.slippage_cost, 0);
  const net = gross - brokerage - taxes;

  const bridge = [
    { k: "Gross P&L", v: gross },
    { k: "Brokerage", v: -brokerage },
    { k: "Taxes", v: -taxes },
    { k: "Net P&L", v: net },
  ];

  const byReason = Object.entries(
    result.trades.reduce<Record<string, { pnl: number; n: number }>>(
      (acc, t) => {
        const e = (acc[t.exit_reason] ??= { pnl: 0, n: 0 });
        e.pnl += t.net_pnl;
        e.n += 1;
        return acc;
      },
      {},
    ),
  ).map(([k, v]) => ({ k: `${k} (${v.n})`, v: Math.round(v.pnl) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          What the strategy was and how P&amp;L is calculated
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 text-sm">
        <section className="space-y-3">
          <h3 className="font-semibold">1. Strategy</h3>
          {spec.description && (
            <p className="text-muted-foreground">{spec.description}</p>
          )}
          <Rules
            title="Bullish signal (market expected to rise)"
            c={spec.entry_bullish}
            spec={spec}
          />
          <Rules
            title="Bearish signal (market expected to fall)"
            c={spec.entry_bearish}
            spec={spec}
          />
          <Rules title="Exit signal" c={spec.exit_condition} spec={spec} />
          {spec.exit_on_opposite_signal && (
            <p className="text-muted-foreground">
              The position is closed as soon as the opposite signal appears.
            </p>
          )}
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>
              The signal is checked on the close of each underlying (index)
              candle, and the order is filled at the{" "}
              <b>open of the next candle</b>.
            </li>
            <li>
              On a bullish signal it{" "}
              {buy ? "buys a CALL (CE)" : "sells a PUT (PE)"}; on a bearish
              signal it {buy ? "buys a PUT (PE)" : "sells a CALL (CE)"}. Strike:{" "}
              {spec.instrument.strike.mode}
              {spec.instrument.strike.mode === "offset"
                ? ` ${spec.instrument.strike.offset}`
                : ""}
              , expiry: {spec.instrument.expiry}. Size: {spec.lots} lot(s).
            </li>
            <li>
              Risk:{" "}
              {[
                r.stop_loss_pct &&
                  `stop-loss ${r.stop_loss_pct}% (of the entry premium)`,
                r.target_pct && `target ${r.target_pct}%`,
                r.trailing_sl_pct && `trailing SL ${r.trailing_sl_pct}%`,
                r.max_trades_per_day &&
                  `max ${r.max_trades_per_day} trades/day`,
              ]
                .filter(Boolean)
                .join(", ") || "no stop-loss or target"}
              . Entry {String(r.entry_start).slice(0, 5)}–
              {String(r.entry_end).slice(0, 5)}, all positions are squared off
              at {String(r.square_off).slice(0, 5)}.
            </li>
          </ul>
        </section>

        <section className="space-y-3">
          <h3 className="font-semibold">
            2. How profit and loss are calculated
          </h3>
          <div className="rounded-lg bg-muted/40 p-3 font-mono text-xs leading-6">
            Gross P&amp;L = (Exit price − Entry price) × Qty
            {buy ? "" : "  × (−1, because this is a sell trade)"}
            <br />
            Brokerage = {money(spec.costs.brokerage_per_order)} × 2 orders
            (entry + exit)
            <br />
            Taxes = {spec.costs.tax_pct}% × (Entry + Exit price) × Qty
            <br />
            <b>Net P&amp;L = Gross − Brokerage − Taxes</b>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Qty = lots × lot size (NSE changes the lot size by expiry).</li>
            <li>
              Slippage ({spec.costs.slippage.value}
              {spec.costs.slippage.mode === "pct" ? "%" : " points"}) is already
              built into the fill price: buys fill higher, sells fill lower. So
              it is already inside Gross P&amp;L (this run: {money(slip)}) and
              is not subtracted again.
            </li>
            <li>
              Equity curve = starting capital {money(run.capital)} + the Net
              P&amp;L of all trades so far. Drawdown = how far equity is below
              its previous peak.
            </li>
          </ul>
          {t0 && (
            <div className="rounded-lg border p-3 text-xs">
              <div className="mb-1 font-medium">
                Example: trade #{t0.id} ({t0.strike} {t0.option_type})
              </div>
              ({num(t0.exit_price)} − {num(t0.entry_price)}) × {t0.qty}
              {buy ? "" : " × −1"} = <b>{money(t0.gross_pnl)}</b> gross; −{" "}
              {money(t0.brokerage)} brokerage − {money(t0.taxes)} taxes ={" "}
              <b
                className={t0.net_pnl >= 0 ? "text-green-600" : "text-red-600"}
              >
                {money(t0.net_pnl)} net
              </b>
              . Exit reason: {t0.exit_reason}.
            </div>
          )}
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <MiniChart
            title="Gross to Net P&L (whole run)"
            note={`Gross ${money(gross)} minus costs (${money(brokerage + taxes)}) leaves a Net of ${money(net)}.`}
            data={bridge}
          />
          <MiniChart
            title="Net P&L by exit reason"
            note="Shows which exits (stop_loss, target, square_off…) make money and which lose it. The number of trades is in brackets."
            data={byReason}
          />
        </section>
      </CardContent>
    </Card>
  );
}

function MiniChart({
  title,
  note,
  data,
}: {
  title: string;
  note: string;
  data: { k: string; v: number }[];
}) {
  return (
    <div>
      <div className="mb-1 font-medium">{title}</div>
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="k" fontSize={11} interval={0} />
            <YAxis tickFormatter={money} width={80} fontSize={11} />
            <Tooltip formatter={(v) => [money(Number(v)), "P&L"]} />
            <ReferenceLine y={0} stroke={GRID} />
            <Bar isAnimationActive={false} dataKey="v">
              {data.map((d) => (
                <Cell key={d.k} fill={d.v >= 0 ? GREEN : RED} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{note}</p>
    </div>
  );
}
