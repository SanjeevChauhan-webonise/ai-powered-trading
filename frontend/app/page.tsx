"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API_URL, api, type Health } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="mb-6 text-2xl font-semibold">Options Strategy Backtester</h1>
      <Link href="/backtest/new" className={`${buttonVariants()} mb-6`}>
        Run a backtest
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>Backend status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {error && <p className="text-red-600">Cannot reach {API_URL}: {error}</p>}
          {!health && !error && <p>Checking…</p>}
          {health && (
            <>
              <div className="flex items-center gap-2">
                <Badge variant={health.status === "ok" ? "default" : "destructive"}>
                  {health.status}
                </Badge>
                <span className="text-sm text-muted-foreground">v{health.version}</span>
              </div>
              <ul className="text-sm">
                {Object.entries(health.services).map(([name, s]) => (
                  <li key={name}>
                    {name}: {s}
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
