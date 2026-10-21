"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, type Level } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LEVELS } from "@/lib/levels";

// Fake test accounts created by otj/seed_users.py. Shown only while NEXT_PUBLIC_DEMO_LOGINS is not "false".
const DEMO_PASSWORD = "Test@12345";
const OWNER_EMAIL = process.env.NEXT_PUBLIC_OWNER_EMAIL; // your own account; set it in .env.local (not committed)
const DEMO = [
  ...(OWNER_EMAIL ? [{ name: "You (advanced)", email: OWNER_EMAIL }] : []),
  { name: "Amit (beginner)", email: "amit@example.com" },
  { name: "Priya (advanced)", email: "priya@example.com" },
  { name: "Rahul (expert)", email: "rahul@example.com" },
  { name: "Sneha (beginner)", email: "sneha@example.com" },
];
const label = "mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

export default function LoginPage() {
  const router = useRouter();
  const { user, ready, signIn } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [level, setLevel] = useState<Level>("beginner");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const showDemo = process.env.NEXT_PUBLIC_DEMO_LOGINS !== "false";

  useEffect(() => {
    if (ready && user) router.replace("/");
  }, [ready, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.register({ email, name, password, level });
      signIn(res);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 p-6">
      <div>
        <div className="text-2xl font-semibold tracking-tight">Strike AI</div>
        <div className="text-sm text-muted-foreground">Options Strategy Lab · NSE · educational use only</div>
      </div>
      <Card>
        <CardContent className="space-y-4 py-5">
          <h1 className="text-lg font-semibold">{mode === "login" ? "Log in" : "Create an account"}</h1>
          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <div>
                <label className={label} htmlFor="name">Name</label>
                <Input id="name" className="h-10 bg-background" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
              </div>
            )}
            <div>
              <label className={label} htmlFor="email">Email</label>
              <Input id="email" type="email" autoComplete="email" className="h-10 bg-background" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className={label} htmlFor="pw">Password</label>
              <Input
                id="pw"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="h-10 bg-background"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={mode === "register" ? 8 : undefined}
              />
              {mode === "register" && <p className="mt-1 text-xs text-muted-foreground">At least 8 characters.</p>}
            </div>
            {mode === "register" && (
              <div>
                <span className={label}>Your experience</span>
                <div className="space-y-2">
                  {LEVELS.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => setLevel(l.id)}
                      className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${level === l.id ? "border-primary bg-primary/10" : "hover:bg-muted"}`}
                    >
                      <div className="text-sm font-semibold">{l.label}</div>
                      <div className="text-xs text-muted-foreground">{l.blurb}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
            <Button type="submit" className="h-10 w-full font-semibold" disabled={busy}>
              {busy && <LoaderCircle className="animate-spin" />}
              {mode === "login" ? "Log in" : "Create account"}
            </Button>
          </form>
          <button
            type="button"
            className="text-sm text-primary hover:underline"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "New here? Create an account" : "Already have an account? Log in"}
          </button>
        </CardContent>
      </Card>

      {showDemo && mode === "login" && (
        <Card>
          <CardContent className="space-y-2 py-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Demo accounts (fake test data)</div>
            <div className="flex flex-wrap gap-2">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  className="rounded-lg border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                  onClick={() => {
                    setEmail(d.email);
                    setPassword(DEMO_PASSWORD);
                  }}
                >
                  {d.name}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Click one to fill the form, then Log in. Password for all: <span className="font-mono">{DEMO_PASSWORD}</span></p>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
