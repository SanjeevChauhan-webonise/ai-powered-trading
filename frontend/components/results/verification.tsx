"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { BacktestResult } from "@/lib/api";
import { money } from "@/lib/format";

const COLUMNS = [
  "id",
  "side",
  "option_type",
  "expiry",
  "strike",
  "signal_time",
  "entry_time",
  "exit_time",
  "lots",
  "lot_size",
  "qty",
  "entry_raw",
  "entry_price",
  "exit_raw",
  "exit_price",
  "stop_price",
  "target_price",
  "trail_stop_price",
  "exit_reason",
  "gross_pnl",
  "slippage_cost",
  "brokerage",
  "taxes",
  "net_pnl",
  "verified",
] as const;

function downloadCsv(result: BacktestResult, name: string) {
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = result.trades.map((t) =>
    COLUMNS.map((c) => esc((t as unknown as Record<string, unknown>)[c])).join(
      ",",
    ),
  );
  const blob = new Blob([[COLUMNS.join(","), ...rows].join("\n")], {
    type: "text/csv",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${name.replace(/[^\w-]+/g, "_")}_trades.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** System check summary + a CSV of every trade with its audit columns, so the result can be re-done in a spreadsheet. */
export function VerificationBanner({ result }: { result: BacktestResult }) {
  const v = result.verification;
  const ok = v ? v.failed === 0 && v.totals_match : null;
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4 text-sm">
        <div className="space-y-1">
          <div className="font-semibold">
            Verification{" "}
            {v && (
              <span className={ok ? "text-green-700" : "text-red-700"}>
                {ok ? "· all trades reconcile" : "· mismatch found"}
              </span>
            )}
          </div>
          {v ? (
            <p className="text-xs text-muted-foreground">
              System check: {v.passed} of {v.checked} trades re-computed from
              their raw candles, prices, slippage and costs match the engine.
              Sum of trade P&amp;L {money(v.sum_of_trades)}{" "}
              {v.totals_match ? "=" : "≠"} reported total{" "}
              {money(v.reported_total_pnl)}
              {v.failed > 0
                ? `. Check trades: ${v.failed_trade_ids.slice(0, 15).join(", ")}${v.failed > 15 ? "…" : ""}.`
                : "."}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              This backtest was stored before the system check existed. Use
              &quot;Edit &amp; re-run&quot; to get it.
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            To check by hand: click ▸ on any trade below for the arithmetic and
            the option candles, or download the CSV and recompute in a
            spreadsheet.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => downloadCsv(result, result.strategy_name)}
        >
          Download trades (CSV)
        </Button>
      </CardContent>
    </Card>
  );
}
