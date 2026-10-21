"use client";

import { ErrorNote, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api, type Level } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LEVELS } from "@/lib/levels";
import { useLoad } from "@/lib/use-load";

function Profile() {
  const { user, setUser, signOut } = useAuth();
  const [saving, setSaving] = useState<Level | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;

  async function choose(level: Level) {
    setSaving(level);
    setError(null);
    try {
      setUser(await api.updateMe({ level }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Your profile</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div>
          <div className="font-medium">{user.name}</div>
          <div className="text-muted-foreground">{user.email}</div>
        </div>
        <div>
          <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Experience level</div>
          <div className="grid gap-2 sm:grid-cols-3">
            {LEVELS.map((l) => (
              <button
                key={l.id}
                type="button"
                disabled={saving !== null}
                onClick={() => void choose(l.id)}
                className={`rounded-lg border p-3 text-left transition-colors ${user.level === l.id ? "border-primary bg-primary/10" : "hover:bg-muted"}`}
              >
                <div className="font-semibold">{l.label}</div>
                <div className="mt-1 text-xs text-muted-foreground">{l.blurb}</div>
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            The level tunes how the agents explain things and which risk guardrails apply to your trade plans.
          </p>
        </div>
        {error && <ErrorNote message={error} />}
        <Button variant="outline" onClick={() => void signOut()}>Log out</Button>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data, error } = useLoad(() => Promise.all([api.models(), api.health()]));
  const [models, health] = data ?? [null, null];
  const providers = new Map<string, string[]>();
  for (const m of models?.models ?? []) providers.set(m.provider, [...(providers.get(m.provider) ?? []), m.id]);

  return (
    <main className="mx-auto max-w-4xl space-y-5 p-6">
      <PageHeader
        title="Settings & Models"
        description="Read-only. Models and keys are configured in the backend .env file (see .env.example)."
      />
      {error && <ErrorNote message={error} />}
      <Profile />
      <Card>
        <CardHeader><CardTitle className="text-base">Default model</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-mono">{models?.default ?? "–"}</span>
            {models && (
              <Badge className={models.default_available ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}>
                {models.default_available ? "provider configured" : "provider not configured"}
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground">
            Per-agent overrides: RESEARCH_MODEL, STRATEGY_MODEL, VERIFY_MODEL, BACKTEST_MODEL, RISK_MODEL. Azure OpenAI ids look like
            azure:&lt;deployment&gt;.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Available models</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          {models && providers.size === 0 && (
            <p className="text-muted-foreground">No provider is configured. Set an API key (or ENABLE_MOCK_LLM=true for the offline demo model).</p>
          )}
          {[...providers.entries()].map(([p, ids]) => (
            <div key={p}>
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{p}</div>
              <div className="flex flex-wrap gap-1.5">
                {ids.map((id) => (
                  <span key={id} className={`rounded px-2 py-0.5 font-mono text-xs ${id === models?.default ? "bg-primary/10 text-primary" : "bg-muted"}`}>{id}</span>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Backend services</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm">
          {health && Object.entries(health.services).map(([name, s]) => (
            <div key={name} className="flex items-center gap-2">
              <span className={`size-2 rounded-full ${s === "up" ? "bg-emerald-500" : "bg-red-500"}`} />
              <span className="w-24">{name}</span><span className="text-muted-foreground">{s}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </main>
  );
}
