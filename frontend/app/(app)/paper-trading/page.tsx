"use client";

import { useCallback, useEffect, useState } from "react";

import { ErrorNote, PageHeader, PnlText } from "@/components/layout/page-header";
import { MarketClock } from "@/components/paper/market-clock";
import { OrderTicket } from "@/components/paper/order-ticket";
import { Orders, Positions, Trades } from "@/components/paper/tables";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  api,
  type Dataset,
  type PaperAccount,
  type PaperOrder,
  type PaperPosition,
  type PaperTrade,
} from "@/lib/api";
import { money } from "@/lib/format";

interface Data {
  account: PaperAccount;
  positions: PaperPosition[];
  trades: PaperTrade[];
  orders: PaperOrder[];
}

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

export default function PaperTradingPage() {
  const [data, setData] = useState<Data | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [exits, setExits] = useState<PaperTrade[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [account, positions, trades, orders] = await Promise.all([
      api.paperAccount(),
      api.paperPositions(),
      api.paperTrades(),
      api.paperOrders(),
    ]);
    setData({ account, positions, trades, orders });
  }, []);

  useEffect(() => {
    let on = true;
    Promise.all([api.paperAccount(), api.paperPositions(), api.paperTrades(), api.paperOrders(), api.datasets()])
      .then(([account, positions, trades, orders, ds]) => {
        if (!on) return;
        setData({ account, positions, trades, orders });
        setDatasets(ds);
      })
      .catch((e: Error) => on && setError(e.message));
    return () => {
      on = false;
    };
  }, []);

  async function reset() {
    const text = window.prompt("Reset the paper account? Positions, orders and trades are deleted. Starting balance in rupees:", String(data?.account.starting_balance ?? 500000));
    if (text === null) return;
    const n = Number(text.replace(/,/g, ""));
    if (!Number.isFinite(n) || n <= 0) {
      setError("Enter a positive number for the starting balance.");
      return;
    }
    setError(null);
    try {
      await api.paperReset(n);
      setExits([]);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const a = data?.account;
  const reasons: Record<string, string> = { stop: "stop loss", target: "target", squareoff: "square-off", expiry: "expiry", manual: "manual" };
  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <PageHeader
        title="Paper Trading"
        description="Practice with virtual money. Prices come from a dataset replayed by a clock (simulation, not live market data). Nothing is sent to a broker."
        action={<Button variant="outline" size="lg" onClick={() => void reset()}>Reset account</Button>}
      />
      {error && <ErrorNote message={error} />}
      {!data && !error && <p className="text-sm text-muted-foreground">Loading…</p>}

      {a && data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Equity" hint={`started with ${money(a.starting_balance)}`}>{money(a.equity)}</Stat>
            <Stat label="Cash" hint={`${money(a.market_value)} in open positions`}>{money(a.cash)}</Stat>
            <Stat label="Realised P&L" hint="after brokerage and taxes"><PnlText value={a.realized_pnl} /></Stat>
            <Stat label="Unrealised P&L" hint={`${a.open_positions} open position(s)`}><PnlText value={a.unrealized_pnl} /></Stat>
          </div>

          {exits.length > 0 && (
            <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950">
              <span className="font-semibold">Closed automatically while the market moved:</span>{" "}
              {exits.map((t) => `${t.strike} ${t.option_type} by ${reasons[t.exit_reason] ?? t.exit_reason} (${t.net_pnl >= 0 ? "+" : ""}${Math.round(t.net_pnl)})`).join(", ")}
            </div>
          )}

          <div className="grid items-start gap-5 xl:grid-cols-[1fr_1.3fr]">
            <MarketClock
              account={a}
              datasets={datasets}
              spot={spot}
              onChange={refresh}
              onExits={setExits}
              onError={setError}
            />
            <OrderTicket account={a} onPlaced={refresh} onChain={setSpot} onError={setError} />
          </div>

          <Positions rows={data.positions} onClosed={refresh} onError={setError} />
          <div className="grid items-start gap-5 xl:grid-cols-2">
            <Trades rows={data.trades} />
            <Orders rows={data.orders} />
          </div>
        </>
      )}
    </main>
  );
}
