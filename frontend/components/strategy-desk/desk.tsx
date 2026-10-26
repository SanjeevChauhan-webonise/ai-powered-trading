"use client";

import { LoaderCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  api,
  type AskAnswer,
  type ModelsResponse,
  type Run,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { STORAGE_PREFIX } from "@/lib/brand";
import {
  daysTo,
  expiryKind,
  expiryLabel,
  expiryNote,
  upcomingExpiries,
  type ExpiryOption,
} from "@/lib/expiries";
import { tradePlanOf } from "@/lib/trade-plan";

import { Answer } from "./answer";
import { Pipeline } from "./pipeline";
import { Recommendation } from "./recommendation";

type Underlying = "NIFTY" | "BANKNIFTY";
const UNDERLYINGS: { id: string; supported: boolean }[] = [
  { id: "NIFTY", supported: true },
  { id: "BANKNIFTY", supported: true },
  { id: "FINNIFTY", supported: false },
  { id: "MIDCPNIFTY", supported: false },
];
const RISK = ["Low", "Medium", "High"] as const;
const RECENT_KEY = `${STORAGE_PREFIX}:recent-queries`;
const EXAMPLES = [
  "BANKNIFTY monthly expiry, EMA 9/21 crossover with RSI, max loss ₹2,000",
  "NIFTY mildly bullish till expiry, max loss ₹7,000. Which strategy fits and why?",
  "NIFTY weekly expiry, buy ATM CE when MACD crosses above signal, stop loss 25%, target 50%",
  "What is the current NIFTY lot size and how many lots fit in ₹1,00,000 capital?",
  "What is theta decay and how does it hurt option buyers near expiry?",
];

const label =
  "mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";
const field = "h-10 bg-background";

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

export function Desk() {
  const params = useSearchParams();
  const { user } = useAuth();
  const runParam = params.get("run");

  const [query, setQuery] = useState("");
  const [underlying, setUnderlying] = useState<Underlying | null>(null);
  const [expiry, setExpiry] = useState("");
  const [capital, setCapital] = useState("");
  const [maxLoss, setMaxLoss] = useState("");
  const [target, setTarget] = useState("");
  const [risk, setRisk] = useState<(typeof RISK)[number]>("Low");
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [model, setModel] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    const t = window.setTimeout(() => setRecent(loadRecent()), 0); // localStorage is browser-only
    api
      .models()
      .then((m) => {
        setModels(m);
        // preselect the server's default model so the dropdown shows it (not just "Default")
        if (m.models.some((x) => x.id === m.default))
          setModel((cur) => cur || m.default);
      })
      .catch(() => undefined);
    return () => {
      alive.current = false;
      window.clearTimeout(t);
    };
  }, []);

  const follow = useCallback(async (id: string) => {
    for (;;) {
      const r = await api.getRun(id);
      if (!alive.current) return;
      setRun(r);
      if (r.status === "completed" || r.status === "failed") return;
      await new Promise((res) => setTimeout(res, 1000));
    }
  }, []);

  // Reopen a run from the dashboard (?run=<id>) and show the request it was made with.
  useEffect(() => {
    if (!runParam) return;
    api
      .getRun(runParam)
      .then((r) => {
        setRun(r);
        const q = r.request;
        setQuery(q.idea ?? "");
        setUnderlying((q.underlying as Underlying | null) ?? null);
        setExpiry(q.expiry ?? "");
        setCapital(String(q.capital));
        setMaxLoss(q.max_loss ? String(q.max_loss) : "");
        setTarget(q.target_profit ? String(q.target_profit) : "");
        if (r.status === "queued" || r.status === "running")
          void follow(r.id).catch(() => undefined);
      })
      .catch((e: Error) => setError(e.message));
  }, [runParam, follow]);

  async function generate(e: React.FormEvent | null, forceStrategy = false) {
    e?.preventDefault();
    if (!query.trim()) {
      setError("Describe your view or trade first.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotes([]);
    setRun(null);
    setAnswer(null);
    try {
      const parsed = await api.parseQuery(query, model);
      if (parsed.intent === "off_topic") {
        setError(
          parsed.refusal ||
            "This tool only handles NIFTY and BANKNIFTY options trading.",
        );
        return;
      }
      if (parsed.intent === "question" && !forceStrategy) {
        setAnswer(await api.ask(query, model)); // a general question: answer it, no plan and no backtest
        return;
      }
      const u = underlying ?? parsed.underlying;
      if (!u)
        throw new Error(
          "Pick an underlying (NIFTY or BANKNIFTY), or mention it in your query.",
        );
      const exp = expiry || parsed.expiry || null;
      const cap = Number(capital) || parsed.capital || 100000;
      const loss = Number(maxLoss) || parsed.max_loss || null;
      const tgt = Number(target) || parsed.target_profit || null;
      setUnderlying(u);
      setExpiry(exp ?? "");
      setNotes(parsed.notes ?? []);
      if (!capital && parsed.capital) setCapital(String(parsed.capital));
      if (!maxLoss && parsed.max_loss) setMaxLoss(String(parsed.max_loss));
      if (!target && parsed.target_profit)
        setTarget(String(parsed.target_profit));

      const created = await api.createRun({
        underlying: u,
        expiry: exp,
        capital: cap,
        max_loss: loss,
        target_profit: tgt,
        idea: `${parsed.idea || query} Risk appetite: ${risk.toLowerCase()}.`,
        model: model || null,
      });
      const next = [query, ...recent.filter((q) => q !== query)].slice(0, 5);
      setRecent(next);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      await follow(created.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  // a date that is not in the list (from your query, or an earlier run) is kept as an extra option
  const listed: ExpiryOption[] = upcomingExpiries(underlying);
  const expiryOptions =
    expiry && underlying && !listed.some((o) => o.date === expiry)
      ? [
          ...listed,
          { date: expiry, kind: expiryKind(expiry), days: daysTo(expiry) },
        ].sort((x, y) => x.date.localeCompare(y.date))
      : listed;
  const plan = tradePlanOf(run);
  const working = busy || run?.status === "queued" || run?.status === "running";

  return (
    <main className="mx-auto max-w-[1400px] space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Strategy Desk
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Describe your view. Five agents research, build, verify, backtest
            and risk-review a strategy for you.
          </p>
        </div>
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[1fr_1.1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ask the agents</CardTitle>
            <CardAction>
              <span className="text-xs text-muted-foreground">Step 1</span>
            </CardAction>
          </CardHeader>
          <CardContent>
            <form onSubmit={generate} className="space-y-4">
              <div>
                <label className={label} htmlFor="q">
                  Your query
                </label>
                <textarea
                  id="q"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  rows={4}
                  placeholder={EXAMPLES[0]}
                  className="w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                />
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">
                    Try an example:
                  </span>
                  {EXAMPLES.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => setQuery(q)}
                      className="max-w-[16rem] truncate rounded-full border bg-muted/50 px-2.5 py-1 text-xs hover:bg-muted"
                      title={q}
                    >
                      {q}
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Name indicators (EMA, RSI, VWAP, Supertrend) to use them;
                  otherwise the agents choose from research and market news. You
                  can also ask a NIFTY / BANKNIFTY options question, such as
                  &quot;what is theta decay?&quot;.
                </p>
              </div>

              <div>
                <span className={label}>Underlying</span>
                <div className="flex flex-wrap gap-2">
                  {UNDERLYINGS.map((u) => (
                    <button
                      key={u.id}
                      type="button"
                      disabled={!u.supported}
                      title={u.supported ? undefined : "Not supported yet"}
                      onClick={() => setUnderlying(u.id as Underlying)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                        underlying === u.id
                          ? "border-primary bg-primary/10 text-primary"
                          : "hover:bg-muted"
                      }`}
                    >
                      {u.id}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className={label} htmlFor="exp">
                  Expiry you plan to trade
                </label>
                <select
                  id="exp"
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                  disabled={!underlying}
                  className="h-10 w-full rounded-lg border bg-background px-2 text-sm disabled:opacity-60"
                >
                  <option value="">
                    {underlying
                      ? "Not specified (read from query / nearest)"
                      : "Pick an underlying first"}
                  </option>
                  {expiryOptions.map((o) => (
                    <option key={o.date} value={o.date}>
                      {expiryLabel(o)}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-muted-foreground">
                  {expiry
                    ? `${daysTo(expiry) >= 0 ? `${daysTo(expiry)} days to expiry` : "Expiry date is in the past"} · ${expiryKind(expiry)}. `
                    : ""}
                  {underlying
                    ? `${expiryNote(underlying)}. Estimated from the usual weekday; a holiday can shift one, so confirm in your broker.`
                    : ""}
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className={label} htmlFor="cap">
                    Capital (₹)
                  </label>
                  <Input
                    id="cap"
                    inputMode="numeric"
                    className={`${field} font-mono`}
                    placeholder="1,00,000"
                    value={capital}
                    onChange={(e) =>
                      setCapital(e.target.value.replace(/[^\d.]/g, ""))
                    }
                  />
                </div>
                <div>
                  <label className={label} htmlFor="ml">
                    Max loss (₹)
                  </label>
                  <Input
                    id="ml"
                    inputMode="numeric"
                    className={`${field} font-mono`}
                    placeholder="per trade"
                    value={maxLoss}
                    onChange={(e) =>
                      setMaxLoss(e.target.value.replace(/[^\d.]/g, ""))
                    }
                  />
                </div>
                <div>
                  <label className={label} htmlFor="tg">
                    Target (₹)
                  </label>
                  <Input
                    id="tg"
                    inputMode="numeric"
                    className={`${field} font-mono`}
                    placeholder="per trade"
                    value={target}
                    onChange={(e) =>
                      setTarget(e.target.value.replace(/[^\d.]/g, ""))
                    }
                  />
                </div>
              </div>
              <p className="-mt-2 text-xs text-muted-foreground">
                Lots are worked out from your max loss (per trade, option
                buying). Blank fields are read from your query.
              </p>

              <div>
                <span className={label}>Risk appetite</span>
                <div className="grid grid-cols-3 gap-1 rounded-xl bg-muted p-1">
                  {RISK.map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setRisk(r)}
                      className={`rounded-lg py-1.5 text-sm font-medium ${risk === r ? "bg-card shadow-sm" : "text-muted-foreground"}`}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className={label} htmlFor="mdl">
                  Model
                </label>
                <select
                  id="mdl"
                  value={models?.locked ? "" : model}
                  disabled={models?.locked}
                  onChange={(e) => setModel(e.target.value)}
                  className="h-10 w-full rounded-lg border bg-background px-2 text-sm"
                >
                  <option value="">Default ({models?.default ?? "…"})</option>
                  {models?.models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id}
                    </option>
                  ))}
                </select>
                {models?.locked && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    The model is fixed by the server ({models.default}).
                  </p>
                )}
                {models?.default.startsWith("mock:") && !model && (
                  <p className="mt-1 text-xs text-amber-700">
                    The default is the offline mock model (scripted, no real
                    reasoning). Pick a real model above.
                  </p>
                )}
              </div>

              {error && (
                <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
                  {error}
                </p>
              )}
              {notes.length > 0 && (
                <ul className="list-disc space-y-0.5 rounded-lg bg-amber-50 py-2 pl-7 pr-3 text-xs text-amber-900">
                  {notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
              {user && (
                <p className="text-xs text-muted-foreground">
                  Answers and guardrails are tuned for your{" "}
                  <span className="font-medium">{user.level}</span> level
                  (change it in Settings).
                </p>
              )}
              <Button
                type="submit"
                className="h-11 w-full text-sm font-semibold"
                disabled={busy}
              >
                {busy && <LoaderCircle className="animate-spin" />}
                {busy ? "Agents are working…" : "Ask or generate strategy"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {answer ? (
          <Answer
            answer={answer}
            onBuildPlan={() => void generate(null, true)}
          />
        ) : (
          <Recommendation run={run} plan={plan} working={working} />
        )}
        <Pipeline
          run={run}
          note={
            answer
              ? "Answered without running the agents or a backtest."
              : undefined
          }
        />
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3 text-sm">
          <span className="font-semibold">Recent queries</span>
          {(recent.length ? recent : EXAMPLES.slice(0, 3)).map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuery(q)}
              className="max-w-md truncate text-primary hover:underline"
              title={q}
            >
              {q}
            </button>
          ))}
        </CardContent>
      </Card>
    </main>
  );
}
