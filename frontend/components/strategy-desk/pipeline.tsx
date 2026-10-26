import { Check, CircleAlert, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Run, RunStep } from "@/lib/api";
import { STEP_LABELS, stepOf, stepSeconds } from "@/lib/trade-plan";

const cut = (s: string, n = 110) =>
  s.length > n ? `${s.slice(0, n - 1)}…` : s;

function describe(step: RunStep): string {
  const o = step.output as Record<string, unknown> | null;
  if (step.status === "skipped") return "Skipped";
  if (step.status === "failed") return cut(step.error ?? "Failed");
  if (step.status === "pending") return "Waiting";
  if (step.status === "running") return "Working…";
  if (!o) return "Done";
  switch (step.name) {
    case "research": {
      const notes = ((o.sources as string[]) ?? []).length;
      const news = ((o.news_sources as string[]) ?? []).length;
      return `${notes} knowledge-base notes · ${news} news sources`;
    }
    case "strategy":
      return cut(String(o.explanation ?? o.source ?? "Strategy built"));
    case "verify": {
      const issues = ((o.issues as unknown[]) ?? []).length;
      const rev = Number(o.revisions ?? 0);
      return `${String(o.verdict ?? "").replace("_", " ")} · ${issues} issue(s)${rev ? ` · revised ${rev}×` : ""}`;
    }
    case "backtest":
      return cut(String(o.notes ?? "Backtest finished"));
    default:
      return cut(
        String(
          (o.review as { summary?: string } | undefined)?.summary ??
            "Review finished",
        ),
      );
  }
}

function Dot({ step, index }: { step: RunStep; index: number }) {
  const base =
    "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold";
  if (step.status === "running")
    return (
      <span className={`${base} bg-primary/10 text-primary`}>
        <LoaderCircle className="size-3.5 animate-spin" />
      </span>
    );
  if (step.status === "completed")
    return (
      <span className={`${base} bg-emerald-100 text-emerald-700`}>
        <Check className="size-3.5" />
      </span>
    );
  if (step.status === "failed")
    return (
      <span className={`${base} bg-red-100 text-red-700`}>
        <CircleAlert className="size-3.5" />
      </span>
    );
  return (
    <span className={`${base} bg-muted text-muted-foreground`}>
      {index + 1}
    </span>
  );
}

export function Pipeline({ run, note }: { run: Run | null; note?: string }) {
  const steps = run?.steps ?? [];
  const review = steps.find((s) => s.name === "risk")?.output?.review as
    | { summary: string; red_flags: { title: string; severity: string }[] }
    | undefined;
  const warnings = steps.flatMap((s) => s.warnings);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Agent pipeline</CardTitle>
        <CardAction>
          <span className="text-xs text-muted-foreground">Step 3</span>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {steps.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {note ?? "Agents run in order once you generate a strategy."}
          </p>
        )}
        <ol className="space-y-3">
          {steps.map((s, i) => (
            <li key={s.name} className="flex gap-3">
              <Dot step={s} index={i} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-semibold">
                    {STEP_LABELS[s.name] ?? s.name}
                  </span>
                  {stepSeconds(s) != null && (
                    <span className="font-mono text-xs text-muted-foreground">
                      {stepSeconds(s)!.toFixed(1)}s
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">{describe(s)}</p>
              </div>
            </li>
          ))}
        </ol>

        {run?.status === "failed" && run.error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800">
            {run.error}
          </p>
        )}
        {review && (
          <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-950">
            <div className="mb-1 font-semibold">Risk review</div>
            <p>{review.summary}</p>
            {review.red_flags.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-xs">
                {review.red_flags.map((f, i) => (
                  <li key={i}>
                    {f.title} ({f.severity})
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {warnings.length > 0 && (
          <ul className="space-y-1 text-xs text-amber-700">
            {warnings.map((w, i) => (
              <li key={i}>⚠ {w}</li>
            ))}
          </ul>
        )}

        <div className="space-y-2">
          {run?.status === "completed" &&
          stepOf(run, "strategy")?.output?.spec != null ? (
            <Link
              href={`/backtest/new?run=${run.id}`}
              className="inline-flex h-10 w-full items-center justify-center rounded-lg border text-sm font-semibold hover:bg-muted"
            >
              Edit &amp; backtest this strategy
            </Link>
          ) : (
            <Button variant="outline" className="h-10 w-full" disabled>
              Edit &amp; backtest this strategy
            </Button>
          )}
          {run?.backtest_run_id ? (
            <Link
              href={`/results/${run.backtest_run_id}`}
              className="inline-flex h-10 w-full items-center justify-center rounded-lg bg-primary text-sm font-semibold text-primary-foreground hover:bg-primary/90"
            >
              Open full backtest results
            </Link>
          ) : (
            <Button className="h-10 w-full" disabled>
              Open full backtest results
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
