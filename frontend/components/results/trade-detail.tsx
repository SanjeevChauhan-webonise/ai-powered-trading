"use client";

import type { BacktestTrade } from "@/lib/api";
import { dateTime, money, num } from "@/lib/format";

const cell = "px-2 py-1 tabular-nums";

/** The hand-check for one trade: the arithmetic in words, the engine's figure next to an independent recomputation,
 * and the option candles between entry and exit so every price can be looked up. */
export function TradeDetail({ t }: { t: BacktestTrade }) {
  const buy = t.side === "buy";
  const checks = t.checks ?? [];
  const candles = t.candles ?? [];
  const level =
    t.exit_reason === "stop_loss"
      ? t.stop_price
      : t.exit_reason === "trailing_sl"
        ? t.trail_stop_price
        : t.exit_reason === "target"
          ? t.target_price
          : null;

  return (
    <div className="space-y-4 rounded-lg bg-muted/40 p-4 text-sm">
      <div>
        <div className="mb-1 font-semibold">How this trade was calculated</div>
        <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
          <li>
            Signal on the underlying at{" "}
            <b className="text-foreground">{dateTime(t.signal_time)}</b>. The
            order fills at the open of the next candle,{" "}
            <b className="text-foreground">{dateTime(t.entry_time)}</b>.
          </li>
          <li>
            {buy ? "Bought" : "Sold"} {t.strike} {t.option_type} ({t.expiry}) at
            open {t.entry_raw != null ? num(t.entry_raw) : "–"}
            {t.entry_raw != null && t.entry_price !== t.entry_raw
              ? `, fill ${num(t.entry_price)} after slippage`
              : ""}
            . Quantity {t.lots ?? "?"} lot × {t.lot_size ?? "?"} ={" "}
            <b className="text-foreground">{t.qty}</b>.
          </li>
          <li>
            Levels:{" "}
            {t.stop_price != null ? `stop ${num(t.stop_price)}` : "no stop"}
            {t.target_price != null
              ? `, target ${num(t.target_price)}`
              : ", no target"}
            {t.trail_stop_price != null
              ? `, trailing stop ${num(t.trail_stop_price)}`
              : ""}
            .
          </li>
          <li>
            Exit <b className="text-foreground">{t.exit_reason}</b> at{" "}
            {dateTime(t.exit_time)}: price{" "}
            {t.exit_raw != null ? num(t.exit_raw) : "–"}
            {level != null ? ` (level ${num(level)})` : ""}, fill{" "}
            {num(t.exit_price)}.
          </li>
          <li>
            Gross = ({num(t.exit_price)} − {num(t.entry_price)}) × {t.qty}
            {buy ? "" : " × −1 (short)"} ={" "}
            <b className="text-foreground">{money(t.gross_pnl)}</b>. Net = gross
            − brokerage {money(t.brokerage)} − taxes {money(t.taxes)} ={" "}
            <b className="text-foreground">{money(t.net_pnl)}</b>.
          </li>
        </ol>
      </div>

      {checks.length > 0 && (
        <div>
          <div className="mb-1 font-semibold">
            Engine vs independent recomputation{" "}
            <span className={t.verified ? "text-green-700" : "text-red-700"}>
              {t.verified ? "· all match" : "· mismatch"}
            </span>
          </div>
          <table className="w-full text-xs">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className={cell}>Item</th>
                <th className={`${cell} text-right`}>Engine reported</th>
                <th className={`${cell} text-right`}>Recomputed</th>
                <th className={cell}>Match</th>
                <th className={cell}>How</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.name} className="border-t">
                  <td className={cell}>{c.name}</td>
                  <td className={`${cell} text-right`}>
                    {c.reported != null ? num(c.reported) : "–"}
                  </td>
                  <td className={`${cell} text-right`}>
                    {c.recomputed != null ? num(c.recomputed) : "–"}
                  </td>
                  <td
                    className={`${cell} ${c.ok ? "text-green-700" : "font-semibold text-red-700"}`}
                  >
                    {c.ok ? "✓" : "✗"}
                  </td>
                  <td className="px-2 py-1 text-muted-foreground">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {candles.length > 0 && (
        <div>
          <div className="mb-1 font-semibold">
            Option candles from entry to exit ({candles.length})
          </div>
          <div className="max-h-56 overflow-auto rounded border bg-background">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-background text-left text-muted-foreground">
                <tr>
                  <th className={cell}>Time</th>
                  <th className={`${cell} text-right`}>Open</th>
                  <th className={`${cell} text-right`}>High</th>
                  <th className={`${cell} text-right`}>Low</th>
                  <th className={`${cell} text-right`}>Close</th>
                  <th className={cell} />
                </tr>
              </thead>
              <tbody>
                {candles.map((c) => {
                  const entry = c.timestamp === t.entry_time;
                  const exit = c.timestamp === t.exit_time;
                  return (
                    <tr
                      key={c.timestamp}
                      className={`border-t ${entry || exit ? "bg-amber-50" : ""}`}
                    >
                      <td className={cell}>{dateTime(c.timestamp)}</td>
                      <td className={`${cell} text-right`}>{num(c.open)}</td>
                      <td className={`${cell} text-right`}>{num(c.high)}</td>
                      <td className={`${cell} text-right`}>{num(c.low)}</td>
                      <td className={`${cell} text-right`}>{num(c.close)}</td>
                      <td className="px-2 py-1 text-muted-foreground">
                        {entry
                          ? "◀ entry (open)"
                          : exit
                            ? `◀ exit (${t.exit_reason})`
                            : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {checks.length === 0 && (
        <p className="text-xs text-muted-foreground">
          This backtest was stored before the audit trail existed. Re-run it
          (Edit &amp; re-run) to get the full check.
        </p>
      )}
    </div>
  );
}
