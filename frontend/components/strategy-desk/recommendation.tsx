import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Run } from "@/lib/api";
import { money, pct } from "@/lib/format";
import { stepOf, type TradePlan } from "@/lib/trade-plan";

const VERDICT: Record<string, string> = {
  approved: "bg-emerald-100 text-emerald-800",
  needs_changes: "bg-amber-100 text-amber-800",
  rejected: "bg-red-100 text-red-800",
};

function strikeText(plan: TradePlan, side: "CE" | "PE"): string {
  const s = plan.strike;
  const expiry = plan.expiry_date ?? plan.expiry_type;
  if (s.mode === "offset") return `${s.offset >= 0 ? "ATM+" : "ATM"}${s.offset || ""} ${side} · ${expiry}`.replace("ATM+0", "ATM");
  if (s.mode === "nearest_premium") return `${side} near ₹${s.premium} · ${expiry}`;
  return `ATM ${side} · ${expiry}`;
}

function Leg({ plan, label, action }: { plan: TradePlan; label: string; action: string }) {
  const [verb, side] = action.split(" ") as [string, "CE" | "PE"];
  const buy = verb.toLowerCase() === "buy";
  return (
    <tr className="border-t">
      <td className={`px-3 py-3 text-sm font-semibold ${buy ? "text-emerald-700" : "text-red-700"}`}>
        {verb.toUpperCase()}
        <div className="text-[10px] font-normal uppercase text-muted-foreground">{label}</div>
      </td>
      <td className="px-3 py-3 text-sm">{strikeText(plan, side)}</td>
      <td className="px-3 py-3 text-right font-mono text-sm">
        {plan.entry_premium_estimate != null ? plan.entry_premium_estimate.toFixed(2) : "–"}
      </td>
    </tr>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={`font-mono text-base font-semibold ${
          tone === "good" ? "text-emerald-700" : tone === "bad" ? "text-red-700" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export function Recommendation({ run, plan, working }: { run: Run | null; plan: TradePlan | null; working: boolean }) {
  const sources = ((stepOf(run, "research")?.output?.sources as string[] | undefined) ?? []).slice(0, 8);
  const lotSize = plan?.quantity && plan.lots ? plan.quantity / plan.lots : null;
  const verdict = plan?.verification.verdict ?? null;

  return (
    <Card>
      <CardHeader>
          <CardTitle className="text-base">AI recommendation</CardTitle>
          <CardAction><span className="text-xs text-muted-foreground">Step 2</span></CardAction>
        </CardHeader>
      <CardContent className="space-y-4">
        {!plan && (
          <p className="rounded-lg bg-muted px-3 py-8 text-center text-sm text-muted-foreground">
            {working
              ? "The agents are working. The recommendation appears here when the pipeline finishes."
              : run?.status === "failed"
                ? "The run failed before a recommendation could be made. See the pipeline."
                : "Ask the agents on the left. Your trade plan with reasons appears here."}
          </p>
        )}
        {plan && (
          <>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="secondary">{plan.expiry_type === "monthly" ? "Monthly expiry" : "Weekly expiry"}</Badge>
              {plan.expiry_date && <Badge variant="secondary">Expiry {plan.expiry_date}</Badge>}
              {verdict && <Badge className={VERDICT[verdict] ?? ""}>Verifier: {verdict.replace("_", " ")}</Badge>}
            </div>
            <h2 className="text-xl font-semibold tracking-tight">
              {plan.underlying} · {plan.strategy}
            </h2>

            <div className="overflow-hidden rounded-xl border">
              <table className="w-full">
                <thead className="bg-muted/60 text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Action</th>
                    <th className="px-3 py-2 font-medium">Contract</th>
                    <th className="px-3 py-2 text-right font-medium">Est. premium</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.bullish_signal_action && (
                    <Leg plan={plan} label="on bullish signal" action={plan.bullish_signal_action} />
                  )}
                  {plan.bearish_signal_action && (
                    <Leg plan={plan} label="on bearish signal" action={plan.bearish_signal_action} />
                  )}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Stat label="Est. max loss / trade" value={money(plan.max_loss_per_trade)} tone="bad" />
              <Stat label="Est. target profit / trade" value={money(plan.target_profit_per_trade)} tone="good" />
              <Stat
                label="Position"
                value={plan.quantity ? `${plan.lots} lot × ${lotSize} = ${plan.quantity}` : `${plan.lots} lot`}
              />
              <Stat
                label="Stop / target"
                value={`${pct(plan.stop_loss_pct, 0)} / ${pct(plan.target_pct, 0)}`}
              />
              <Stat label="Entry window" value={plan.entry_window} />
              <Stat label="Square-off" value={plan.square_off} />
            </div>

            <div className="border-t pt-4">
              <h3 className="mb-2 text-sm font-semibold">Why this strategy</h3>
              {plan.reasons.length > 0 ? (
                <ol className="list-decimal space-y-1.5 pl-5 text-sm">
                  {plan.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm">{plan.explanation || "No reasons were returned."}</p>
              )}
              {plan.when_to_trade && (
                <p className="mt-3 rounded-lg bg-secondary px-3 py-2 text-sm">
                  <span className="font-semibold">When to trade: </span>
                  {plan.when_to_trade}
                </p>
              )}
              {plan.verification.summary && (
                <p className="mt-2 text-xs text-muted-foreground">Verifier: {plan.verification.summary}</p>
              )}
            </div>

            {plan.backtest.num_trades != null && (
              <p className="text-xs text-muted-foreground">
                Backtest on past data: {plan.backtest.num_trades} trades · win rate {pct(plan.backtest.win_rate_pct)} ·
                net P&amp;L {money(plan.backtest.total_pnl)} · max drawdown {pct(plan.backtest.max_drawdown_pct)}
              </p>
            )}
            {sources.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">Sources:</span>
                {sources.map((s) => (
                  <span key={s} className="rounded bg-muted px-1.5 py-0.5 font-mono">
                    {s}
                  </span>
                ))}
              </div>
            )}
            <ul className="space-y-1 text-[11px] text-muted-foreground">
              {plan.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
