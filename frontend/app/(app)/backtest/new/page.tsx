"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Dataset, type Template } from "@/lib/api";
import { stepOf } from "@/lib/trade-plan";

const selectClass = "h-9 w-full rounded-md border bg-background px-2 text-sm";
const pretty = (spec: unknown) => JSON.stringify(spec, null, 2);

function NewBacktest() {
  const router = useRouter();
  const params = useSearchParams();
  const fromRun = params.get("run");
  const fromBacktest = params.get("from");
  const fromTemplate = params.get("template");

  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [source, setSource] = useState(""); // "template:<id>" or "custom"
  const [specText, setSpecText] = useState("");
  const [original, setOriginal] = useState("");
  const [origin, setOrigin] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [capital, setCapital] = useState("100000");
  const [busy, setBusy] = useState<"run" | "synthetic" | "validate" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[] | null>(null); // null = not validated yet, [] = valid

  function load(spec: unknown, label: string) {
    const text = pretty(spec);
    setSpecText(text);
    setOriginal(text);
    setOrigin(label);
    setProblems(null);
  }

  useEffect(() => {
    let on = true;
    (async () => {
      try {
        const [ds, ts] = await Promise.all([api.datasets(), api.templates()]);
        if (!on) return;
        setDatasets(ds);
        setTemplates(ts);
        setDatasetId(ds[0]?.id ?? "");
        if (fromBacktest) {
          const b = await api.getBacktest(fromBacktest);
          if (!on) return;
          load(b.spec, `backtest "${b.strategy_name}"`);
          setSource("custom");
          if (ds.some((d) => d.id === b.dataset_id)) setDatasetId(b.dataset_id);
          setStart(b.start ?? "");
          setEnd(b.end ?? "");
          setCapital(String(b.capital));
        } else if (fromRun) {
          const r = await api.getRun(fromRun);
          const spec = stepOf(r, "strategy")?.output?.spec;
          if (!on) return;
          if (r.status !== "completed")
            throw new Error(
              r.status === "failed"
                ? "That pipeline run failed, so there is no strategy to backtest. Run the Strategy Desk again."
                : "The agent pipeline is still running. Wait for it to finish, then open this again.",
            );
          if (!spec) throw new Error("This run has no strategy yet");
          load(spec, "your Strategy Desk run");
          setSource("custom");
          const rid = r.request.dataset_id;
          if (rid && ds.some((d) => d.id === rid)) setDatasetId(rid);
          setCapital(String(r.request.capital ?? 100000));
        } else {
          const t = ts.find((x) => x.id === fromTemplate) ?? ts[0];
          if (t) {
            load(t.spec, `template "${t.name}"`);
            setSource(`template:${t.id}`);
          }
        }
      } catch (e) {
        if (on) setError((e as Error).message);
      }
    })();
    return () => {
      on = false;
    };
  }, [fromBacktest, fromRun, fromTemplate]);

  const dataset = datasets?.find((d) => d.id === datasetId);
  const edited = specText !== original;

  function pickTemplate(value: string) {
    setSource(value);
    const t = templates.find((x) => `template:${x.id}` === value);
    if (t) load(t.spec, `template "${t.name}"`);
  }

  function parseSpec(): unknown | null {
    try {
      return JSON.parse(specText);
    } catch (e) {
      setError(`The strategy is not valid JSON: ${(e as Error).message}`);
      return null;
    }
  }

  async function validate() {
    setError(null);
    const spec = parseSpec();
    if (spec === null) return;
    setBusy("validate");
    try {
      const res = await api.validateSpec(spec);
      setProblems(res.errors ?? []);
      if (res.valid && res.spec) setSpecText(pretty(res.spec)); // normalized, defaults filled
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function generateSynthetic() {
    setBusy("synthetic");
    setError(null);
    try {
      const ds = await api.createSynthetic();
      setDatasets((prev) => [ds, ...(prev ?? [])]);
      setDatasetId(ds.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const spec = parseSpec();
    if (spec === null) return;
    setBusy("run");
    try {
      const res = await api.runBacktest({
        dataset_id: datasetId,
        spec: spec as never,
        start: start || null,
        end: end || null,
        capital: Number(capital),
      });
      if (res.status === "failed")
        throw new Error(res.error ?? "Backtest failed");
      router.push(`/results/${res.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold">New backtest</h1>
      <form onSubmit={run} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Dataset</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {datasets && datasets.length > 0 ? (
              <select
                aria-label="Dataset"
                className={selectClass}
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
              >
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.underlying}, {d.start_date} → {d.end_date})
                  </option>
                ))}
              </select>
            ) : (
              datasets && (
                <p className="text-sm text-muted-foreground">
                  No datasets yet.
                </p>
              )
            )}
            {dataset && (
              <p className="text-xs text-muted-foreground">
                {dataset.timeframe_minutes}-min candles · lot size{" "}
                {dataset.lot_size} · {dataset.underlying_rows.toLocaleString()}{" "}
                underlying / {dataset.options_rows.toLocaleString()} option rows
              </p>
            )}
            <Button
              type="button"
              variant="outline"
              onClick={generateSynthetic}
              disabled={busy !== null}
            >
              {busy === "synthetic"
                ? "Generating…"
                : "Generate synthetic dataset"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Strategy</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <select
              aria-label="Strategy source"
              className={selectClass}
              value={source}
              onChange={(e) => pickTemplate(e.target.value)}
            >
              {source === "custom" && (
                <option value="custom">Custom ({origin})</option>
              )}
              {templates.map((t) => (
                <option key={t.id} value={`template:${t.id}`}>
                  Template: {t.name}
                </option>
              ))}
            </select>
            {origin && (
              <p className="text-xs text-muted-foreground">
                Loaded from {origin}.
                {edited
                  ? " You have edited it."
                  : " Edit the JSON below to change it before running."}
              </p>
            )}
            <textarea
              aria-label="Strategy spec JSON"
              spellCheck={false}
              value={specText}
              onChange={(e) => {
                setSpecText(e.target.value);
                setProblems(null);
              }}
              rows={18}
              className="w-full resize-y rounded-md border bg-muted/40 p-3 font-mono text-xs outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={validate}
                disabled={!specText || busy !== null}
              >
                {busy === "validate" ? "Checking…" : "Validate"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setSpecText(original);
                  setProblems(null);
                }}
                disabled={!edited}
              >
                Reset
              </Button>
              {problems && problems.length === 0 && (
                <span className="text-sm text-green-700">Valid strategy.</span>
              )}
            </div>
            {problems && problems.length > 0 && (
              <ul className="list-disc space-y-1 rounded-md bg-red-50 py-2 pl-7 pr-3 text-xs text-red-800">
                {problems.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Range and capital</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="start">Start (optional)</Label>
              <Input
                id="start"
                type="date"
                value={start}
                min={dataset?.start_date ?? undefined}
                max={dataset?.end_date ?? undefined}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="end">End (optional)</Label>
              <Input
                id="end"
                type="date"
                value={end}
                min={dataset?.start_date ?? undefined}
                max={dataset?.end_date ?? undefined}
                onChange={(e) => setEnd(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="capital">Capital (₹)</Label>
              <Input
                id="capital"
                type="number"
                min={1}
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button
          type="submit"
          disabled={!datasetId || !specText || busy !== null}
        >
          {busy === "run"
            ? "Running…"
            : edited
              ? "Run edited backtest"
              : "Run backtest"}
        </Button>
      </form>
    </main>
  );
}

export default function NewBacktestPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-3xl p-6 text-sm text-muted-foreground">
          Loading…
        </main>
      }
    >
      <NewBacktest />
    </Suspense>
  );
}
