import { Suspense } from "react";

import { ResultsView } from "@/components/results/results-view";

export default function ResultsPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-6xl p-6">Loading…</main>}>
      <ResultsView />
    </Suspense>
  );
}
