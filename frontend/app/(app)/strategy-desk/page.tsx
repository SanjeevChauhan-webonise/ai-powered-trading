import { Suspense } from "react";

import { Desk } from "@/components/strategy-desk/desk";

export default function StrategyDeskPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
      <Desk />
    </Suspense>
  );
}
