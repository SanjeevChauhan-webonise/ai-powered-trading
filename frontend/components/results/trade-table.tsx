"use client";

import { Fragment, useMemo, useState } from "react";

import { TradeDetail } from "@/components/results/trade-detail";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BacktestTrade } from "@/lib/api";
import { dateTime, money, num, shortDate } from "@/lib/format";

type SortKey =
  | "id"
  | "entry_time"
  | "exit_time"
  | "strike"
  | "qty"
  | "entry_price"
  | "exit_price"
  | "net_pnl"
  | "exit_reason";

const COLUMNS: { key: SortKey; label: string; right?: boolean }[] = [
  { key: "id", label: "#" },
  { key: "entry_time", label: "Entry" },
  { key: "exit_time", label: "Exit" },
  { key: "strike", label: "Instrument" },
  { key: "qty", label: "Qty (lots × lot size)", right: true },
  { key: "entry_price", label: "Entry ₹", right: true },
  { key: "exit_price", label: "Exit ₹", right: true },
  { key: "net_pnl", label: "Net P&L", right: true },
  { key: "exit_reason", label: "Exit reason" },
];

const selectClass = "h-8 rounded-md border bg-background px-2 text-sm";

export function TradeTable({ trades }: { trades: BacktestTrade[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({
    key: "id",
    dir: 1,
  });
  const [type, setType] = useState("all");
  const [reason, setReason] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [open, setOpen] = useState<number | null>(null);

  const reasons = useMemo(
    () => Array.from(new Set(trades.map((t) => t.exit_reason))).sort(),
    [trades],
  );

  const rows = useMemo(() => {
    const filtered = trades.filter(
      (t) =>
        (type === "all" || t.option_type === type) &&
        (reason === "all" || t.exit_reason === reason) &&
        (outcome === "all" ||
          (outcome === "win" ? t.net_pnl > 0 : t.net_pnl <= 0)),
    );
    return filtered.sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
    });
  }, [trades, sort, type, reason, outcome]);

  return (
    <Card>
      <CardHeader className="gap-3">
        <CardTitle>
          Trade log{" "}
          <span className="text-sm font-normal text-muted-foreground">
            ({rows.length} of {trades.length})
          </span>
        </CardTitle>
        <div className="flex flex-wrap gap-2">
          <select
            aria-label="Option type"
            className={selectClass}
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="all">CE + PE</option>
            <option value="CE">CE only</option>
            <option value="PE">PE only</option>
          </select>
          <select
            aria-label="Exit reason"
            className={selectClass}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          >
            <option value="all">All exit reasons</option>
            {reasons.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select
            aria-label="Outcome"
            className={selectClass}
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
          >
            <option value="all">Winners + losers</option>
            <option value="win">Winners</option>
            <option value="loss">Losers</option>
          </select>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.map((c) => (
                <TableHead
                  key={c.key}
                  className={`cursor-pointer select-none ${c.right ? "text-right" : ""}`}
                  onClick={() =>
                    setSort((s) => ({
                      key: c.key,
                      dir: s.key === c.key ? (s.dir === 1 ? -1 : 1) : 1,
                    }))
                  }
                >
                  {c.label}
                  {sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((t) => (
              <Fragment key={t.id}>
                <TableRow>
                  <TableCell>
                    <button
                      type="button"
                      aria-expanded={open === t.id}
                      aria-label={`Show how trade ${t.id} was calculated`}
                      onClick={() => setOpen(open === t.id ? null : t.id)}
                      className="mr-1 text-muted-foreground hover:text-foreground"
                    >
                      {open === t.id ? "▾" : "▸"}
                    </button>
                    {t.id}
                    {t.verified != null && (
                      <span
                        title={
                          t.verified
                            ? "System check: matches the recomputation"
                            : "System check: MISMATCH, open to see which figure"
                        }
                        className={`ml-1 text-xs ${t.verified ? "text-green-600" : "text-red-600"}`}
                      >
                        {t.verified ? "✓" : "✗"}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>{dateTime(t.entry_time)}</TableCell>
                  <TableCell>{dateTime(t.exit_time)}</TableCell>
                  <TableCell>
                    {t.side === "sell" ? "SELL " : ""}
                    {t.strike} {t.option_type}{" "}
                    <span className="text-muted-foreground">
                      {shortDate(t.expiry)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {t.qty}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {num(t.entry_price)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {num(t.exit_price)}
                  </TableCell>
                  <TableCell
                    className={`text-right tabular-nums ${t.net_pnl >= 0 ? "text-green-600" : "text-red-600"}`}
                  >
                    {money(t.net_pnl)}
                  </TableCell>
                  <TableCell>{t.exit_reason}</TableCell>
                </TableRow>
                {open === t.id && (
                  <TableRow>
                    <TableCell
                      colSpan={COLUMNS.length}
                      className="whitespace-normal bg-background"
                    >
                      <TradeDetail t={t} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={COLUMNS.length}
                  className="text-center text-muted-foreground"
                >
                  No trades match the filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
