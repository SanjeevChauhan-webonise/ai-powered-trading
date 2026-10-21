"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Dataset, type Template } from "@/lib/api";

const selectClass = "h-9 w-full rounded-md border bg-background px-2 text-sm";

export default function NewBacktestPage() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [capital, setCapital] = useState("100000");
  const [busy, setBusy] = useState<"run" | "synthetic" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.datasets(), api.templates()])
      .then(([ds, ts]) => {
        setDatasets(ds);
        setTemplates(ts);
        setDatasetId(ds[0]?.id ?? "");
        setTemplateId(ts[0]?.id ?? "");
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const dataset = datasets?.find((d) => d.id === datasetId);
  const template = templates.find((t) => t.id === templateId);

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
    setBusy("run");
    setError(null);
    try {
      const res = await api.runBacktest({
        dataset_id: datasetId,
        template_id: templateId,
        start: start || null,
        end: end || null,
        capital: Number(capital),
      });
      if (res.status === "failed") throw new Error(res.error ?? "Backtest failed");
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
              <select aria-label="Dataset" className={selectClass} value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.underlying}, {d.start_date} → {d.end_date})
                  </option>
                ))}
              </select>
            ) : (
              datasets && <p className="text-sm text-muted-foreground">No datasets yet.</p>
            )}
            {dataset && (
              <p className="text-xs text-muted-foreground">
                {dataset.timeframe_minutes}-min candles · lot size {dataset.lot_size} ·{" "}
                {dataset.underlying_rows.toLocaleString()} underlying / {dataset.options_rows.toLocaleString()} option rows
              </p>
            )}
            <Button type="button" variant="outline" onClick={generateSynthetic} disabled={busy !== null}>
              {busy === "synthetic" ? "Generating…" : "Generate synthetic dataset"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Strategy template</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <select aria-label="Template" className={selectClass} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            {template && (
              <>
                <p className="text-sm text-muted-foreground">{template.description}</p>
                <details>
                  <summary className="cursor-pointer text-sm">View spec JSON</summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(template.spec, null, 2)}
                  </pre>
                </details>
              </>
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
              <Input id="start" type="date" value={start} min={dataset?.start_date ?? undefined} max={dataset?.end_date ?? undefined} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="end">End (optional)</Label>
              <Input id="end" type="date" value={end} min={dataset?.start_date ?? undefined} max={dataset?.end_date ?? undefined} onChange={(e) => setEnd(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="capital">Capital (₹)</Label>
              <Input id="capital" type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={!datasetId || !templateId || busy !== null}>
          {busy === "run" ? "Running…" : "Run backtest"}
        </Button>
      </form>
    </main>
  );
}
