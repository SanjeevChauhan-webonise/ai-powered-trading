"use client";

import { LoaderCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type Dataset, type PaperAccount, type PaperTrade } from "@/lib/api";
import { dateTime, money, num } from "@/lib/format";

const label = "mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

export function MarketClock({
  account,
  datasets,
  spot,
  onChange,
  onExits,
  onError,
}: {
  account: PaperAccount;
  datasets: Dataset[];
  spot: number | null;
  onChange: () => Promise<void>;
  onExits: (t: PaperTrade[]) => void;
  onError: (m: string | null) => void;
}) {
  const usable = datasets.filter((d) => d.options_rows > 0 && d.underlying_rows > 0);
  const [pick, setPick] = useState(account.dataset_id ?? usable[0]?.id ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const running = !!account.clock_time;
  const perDay = account.lot_size ? Math.round(375 / (usable.find((d) => d.id === account.dataset_id)?.timeframe_minutes || 5)) : 75;
  const atEnd = !!account.clock_time && account.clock_time === account.clock_end;

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    onError(null);
    try {
      await fn();
      await onChange();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  const advance = (candles: number, name: string) =>
    act(name, async () => {
      const r = await api.paperAdvance(candles);
      onExits(r.exits);
    });

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Market clock (replay)</CardTitle></CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-xs text-muted-foreground">
          There is no live feed. The market is a loaded dataset replayed by this clock: orders fill at the price of the
          candle the clock is on, and stops, targets, square-off and expiry run as it moves.
        </p>
        <div>
          <label className={label} htmlFor="ds">Dataset to replay</label>
          <div className="flex gap-2">
            <select id="ds" value={pick} onChange={(e) => setPick(e.target.value)} className="h-9 min-w-0 flex-1 rounded-lg border bg-background px-2 text-sm">
              {usable.length === 0 && <option value="">No dataset with option candles</option>}
              {usable.map((d) => (
                <option key={d.id} value={d.id}>{d.name} · {d.underlying} · {d.timeframe_minutes ?? "?"}m</option>
              ))}
            </select>
            <Button variant="outline" disabled={!pick || busy !== null} onClick={() => void act("start", () => api.paperStartClock(pick))}>
              {busy === "start" && <LoaderCircle className="animate-spin" />}
              {running ? "Restart clock" : "Start clock"}
            </Button>
          </div>
          {running && account.open_positions > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">Restarting needs no open positions (close them or reset the account).</p>
          )}
        </div>

        {running ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className={label}>Market time</div>
                <div className="font-mono font-semibold">{dateTime(account.clock_time!)}</div>
              </div>
              <div>
                <div className={label}>{account.underlying} spot</div>
                <div className="font-mono font-semibold">{spot != null ? money(spot) : "–"}</div>
              </div>
            </div>
            <div>
              <div className={label}>Move the market</div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={busy !== null || atEnd} onClick={() => void advance(1, "a1")}>+1 candle</Button>
                <Button variant="outline" disabled={busy !== null || atEnd} onClick={() => void advance(12, "a12")}>+12 candles</Button>
                <Button variant="outline" disabled={busy !== null || atEnd} onClick={() => void advance(perDay, "aday")}>+1 day</Button>
                <Button variant="outline" disabled={busy !== null || atEnd} onClick={() => void advance(2000, "aend")}>Run to end</Button>
                {busy?.startsWith("a") && <LoaderCircle className="size-4 animate-spin self-center" />}
              </div>
              {atEnd && <p className="mt-1 text-xs text-amber-700">End of the dataset ({dateTime(account.clock_end!)}). Reset or restart to go again.</p>}
            </div>
          </>
        ) : (
          <p className="rounded-lg bg-muted px-3 py-3 text-xs text-muted-foreground">Start the clock to see prices and place orders.</p>
        )}
        <p className="text-[11px] text-muted-foreground">
          Starting balance {money(account.starting_balance)}
          {account.equity !== undefined && <> · equity {money(account.equity)} ({num(((account.equity - account.starting_balance) / account.starting_balance) * 100, 2)}%)</>}
        </p>
      </CardContent>
    </Card>
  );
}
