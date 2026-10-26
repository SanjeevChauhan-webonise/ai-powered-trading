import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { AskAnswer } from "@/lib/api";

/** The answer to a general trading question (no plan, no backtest). */
export function Answer({ answer, onBuildPlan }: { answer: AskAnswer; onBuildPlan: () => void }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-base">Answer</CardTitle>
        <span className="text-xs text-muted-foreground">from the knowledge base and news</span>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="whitespace-pre-wrap">{answer.answer}</p>
        {answer.key_points && answer.key_points.length > 0 && (
          <ul className="list-disc space-y-1 pl-5">
            {answer.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
        {answer.caveats && answer.caveats.length > 0 && (
          <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-950">
            <div className="mb-1 font-semibold">Keep in mind</div>
            <ul className="list-disc space-y-0.5 pl-4">
              {answer.caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}
        {answer.sources && answer.sources.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Sources:</span>
            {answer.sources.map((s) => (
              <span key={s} className="rounded bg-muted px-1.5 py-0.5 font-mono">
                {s}
              </span>
            ))}
          </div>
        )}
        {answer.suggest_strategy_desk && (
          <Button variant="outline" onClick={onBuildPlan}>
            Generate a strategy from this question
          </Button>
        )}
        <p className="text-[11px] text-muted-foreground">Educational only, not financial advice. No live prices are used.</p>
      </CardContent>
    </Card>
  );
}
