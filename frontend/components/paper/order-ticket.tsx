"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, type PaperAccount, type PaperChain } from "@/lib/api";
import { money, num } from "@/lib/format";

const label = "mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

export function OrderTicket({
  account,
  onPlaced,
  onChain,
  onError,
}: {
  account: PaperAccount;
  onPlaced: () => Promise<void>;
  onChain: (spot: number | null) => void;
  onError: (m: string | null) => void;
}) {
  const [expiries, setExpiries] = useState<string[]>([]);
  const [expiry, setExpiry] = useState("");
  const [chain, setChain] = useState<PaperChain | null>(null);
  const [lots, setLots] = useState("1");
  const [stop, setStop] = useState("20");
  const [target, setTarget] = useState("40");
  const [busy, setBusy] = useState<string | null>(null);
  const clock = account.clock_time;

  // The list of expiries (and the chain) depends on the market time, so reload them when the clock moves.
  useEffect(() => {
    if (!clock) return;
    let on = true;
    api
      .paperExpiries()
      .then((r) => {
        if (!on) return;
        setExpiries(r.expiries);
        setExpiry((cur) => (r.expiries.includes(cur) ? cur : (r.expiries[0] ?? "")));
      })
      .catch(() => on && setExpiries([]));
    return () => {
      on = false;
    };
  }, [clock]);

  useEffect(() => {
    if (!clock || !expiry) return;
    let on = true;
    api
      .paperChain(expiry)
      .then((c) => {
        if (!on) return;
        setChain(c);
        onChain(c.spot);
      })
      .catch(() => on && setChain(null));
    return () => {
      on = false;
    };
  }, [clock, expiry, onChain]);

  async function buy(strike: number, type: "CE" | "PE") {
    setBusy(`${strike}${type}`);
    onError(null);
    try {
      await api.paperBuy({
        expiry,
        strike,
        option_type: type,
        lots: Math.max(1, Number(lots) || 1),
        stop_pct: Number(stop) || null,
        target_pct: Number(target) || null,
      });
      await onPlaced();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const atm = chain && chain.spot != null ? chain.rows.reduce((b, r) => (Math.abs(r.strike - chain.spot!) < Math.abs(b.strike - chain.spot!) ? r : b), chain.rows[0]) : null;
  const qty = (Math.max(1, Number(lots) || 1)) * (account.lot_size ?? 1);

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Order ticket · buy an option</CardTitle></CardHeader>
      <CardContent className="space-y-4 text-sm">
        {!clock ? (
          <p className="rounded-lg bg-muted px-3 py-6 text-center text-xs text-muted-foreground">Start the market clock first.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="sm:col-span-2">
                <label className={label} htmlFor="pe">Expiry</label>
                <select id="pe" value={expiry} onChange={(e) => setExpiry(e.target.value)} className="h-9 w-full rounded-lg border bg-background px-2 text-sm">
                  {expiries.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>
              <div>
                <label className={label} htmlFor="pl">Lots</label>
                <Input id="pl" inputMode="numeric" className="h-9 bg-background font-mono" value={lots} onChange={(e) => setLots(e.target.value.replace(/\D/g, ""))} />
              </div>
              <div className="flex items-end text-xs text-muted-foreground">qty {qty}</div>
              <div>
                <label className={label} htmlFor="ps">Stop %</label>
                <Input id="ps" inputMode="decimal" className="h-9 bg-background font-mono" value={stop} onChange={(e) => setStop(e.target.value.replace(/[^\d.]/g, ""))} />
              </div>
              <div>
                <label className={label} htmlFor="pt">Target %</label>
                <Input id="pt" inputMode="decimal" className="h-9 bg-background font-mono" value={target} onChange={(e) => setTarget(e.target.value.replace(/[^\d.]/g, ""))} />
              </div>
            </div>
            <div className="max-h-80 overflow-y-auto rounded-xl border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted text-[10px] uppercase tracking-wide text-muted-foreground">
                  <tr><th className="px-3 py-2 text-right">CE price</th><th className="px-3 py-2 text-center">Strike</th><th className="px-3 py-2 text-left">PE price</th></tr>
                </thead>
                <tbody>
                  {chain?.rows.map((r) => {
                    const isAtm = atm?.strike === r.strike;
                    return (
                      <tr key={r.strike} className={`border-t ${isAtm ? "bg-primary/5" : ""}`}>
                        <td className="px-3 py-1.5 text-right">
                          {r.ce != null && (
                            <button type="button" disabled={busy !== null} onClick={() => void buy(r.strike, "CE")} className="rounded-md border px-2 py-0.5 font-mono text-xs hover:bg-emerald-50">
                              {busy === `${r.strike}CE` ? "…" : `Buy ${num(r.ce)}`}
                            </button>
                          )}
                        </td>
                        <td className="px-3 py-1.5 text-center font-mono font-semibold">{r.strike}{isAtm && <span className="ml-1 text-[10px] text-primary">ATM</span>}</td>
                        <td className="px-3 py-1.5 text-left">
                          {r.pe != null && (
                            <button type="button" disabled={busy !== null} onClick={() => void buy(r.strike, "PE")} className="rounded-md border px-2 py-0.5 font-mono text-xs hover:bg-emerald-50">
                              {busy === `${r.strike}PE` ? "…" : `Buy ${num(r.pe)}`}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {chain && chain.rows.length === 0 && (
                    <tr><td colSpan={3} className="px-3 py-6 text-center text-xs text-muted-foreground">No prices for this expiry at the market time.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              Click a price to buy {Math.max(1, Number(lots) || 1)} lot(s) at it. Cost {chain ? "" : "…"} is the price × {qty}; cash left {money(account.cash)}.
              {busy && <LoaderCircle className="ml-2 inline size-3 animate-spin" />}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
