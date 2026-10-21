"use client";

import Link from "next/link";
import { useState } from "react";

import { PnlText } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type PaperOrder, type PaperPosition, type PaperTrade } from "@/lib/api";
import { dateTime, num } from "@/lib/format";

const contract = (p: { underlying: string; expiry: string; strike: number; option_type: string }) =>
  `${p.underlying} ${p.expiry.slice(5)} ${p.strike} ${p.option_type}`;

const REASON: Record<string, string> = {
  manual: "bg-muted text-foreground",
  stop: "bg-red-100 text-red-800",
  target: "bg-emerald-100 text-emerald-800",
  squareoff: "bg-amber-100 text-amber-800",
  expiry: "bg-violet-100 text-violet-800",
};

export function Positions({
  rows,
  onClosed,
  onError,
}: {
  rows: PaperPosition[];
  onClosed: () => Promise<void>;
  onError: (m: string | null) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  async function close(id: string) {
    setBusy(id);
    onError(null);
    try {
      await api.paperClose(id);
      await onClosed();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Open positions</CardTitle></CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No open positions. Buy from the order ticket, or paper-trade a plan from the Strategy Desk.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Contract</TableHead><TableHead className="text-right">Lots</TableHead>
                <TableHead className="text-right">Avg</TableHead><TableHead className="text-right">Mark</TableHead>
                <TableHead className="text-right">Unrealised</TableHead><TableHead>Exits</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">
                    {contract(p)}
                    {p.run_id && (
                      <Link href={`/strategy-desk?run=${p.run_id}`} className="ml-2 text-xs text-primary hover:underline">plan</Link>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono">{p.lots}</TableCell>
                  <TableCell className="text-right font-mono">{num(p.avg_price)}</TableCell>
                  <TableCell className="text-right font-mono">{num(p.mark_price)}</TableCell>
                  <TableCell className="text-right"><PnlText value={p.unrealized_pnl} /></TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {[p.stop_pct != null && `stop ${p.stop_pct}%`, p.target_pct != null && `target ${p.target_pct}%`, p.square_off && `sq-off ${p.square_off}`].filter(Boolean).join(" · ") || "none"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void close(p.id)}>
                      {busy === p.id ? "…" : "Sell to close"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function Trades({ rows }: { rows: PaperTrade[] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Closed trades ({rows.length})</CardTitle></CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No closed trades yet.</p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Exit time</TableHead><TableHead>Contract</TableHead>
                  <TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Entry → exit</TableHead>
                  <TableHead>Exit</TableHead><TableHead className="text-right">Net P&amp;L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="text-xs text-muted-foreground">{dateTime(t.exit_time)}</TableCell>
                    <TableCell>{contract(t)}</TableCell>
                    <TableCell className="text-right font-mono">{t.qty}</TableCell>
                    <TableCell className="text-right font-mono">{num(t.entry_price)} → {num(t.exit_price)}</TableCell>
                    <TableCell><Badge className={`${REASON[t.exit_reason] ?? ""} whitespace-nowrap`}>{t.exit_reason === "squareoff" ? "sq-off" : t.exit_reason}</Badge></TableCell>
                    <TableCell className="text-right" title={`gross ${num(t.gross_pnl)}, costs ${num(t.costs)}`}><PnlText value={t.net_pnl} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function Orders({ rows }: { rows: PaperOrder[] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Recent orders</CardTitle></CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No orders yet.</p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Market time</TableHead><TableHead>Contract</TableHead><TableHead>Side</TableHead>
                  <TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Price</TableHead><TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="text-xs text-muted-foreground">{dateTime(o.placed_at)}</TableCell>
                    <TableCell>{contract(o)}</TableCell>
                    <TableCell className={o.side === "buy" ? "font-semibold text-emerald-700" : "font-semibold text-red-700"}>{o.side.toUpperCase()}</TableCell>
                    <TableCell className="text-right font-mono">{o.qty}</TableCell>
                    <TableCell className="text-right font-mono">{num(o.price)}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs" title={o.note ?? undefined}>
                      {o.status === "rejected" ? <span className="text-red-700">rejected</span> : `filled${o.source === "manual" ? "" : ` · ${o.source}`}`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
