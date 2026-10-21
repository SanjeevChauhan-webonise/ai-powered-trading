"use client";

import {
  BookOpen,
  ChartColumn,
  ChartLine,
  ClipboardList,
  LayoutDashboard,
  Settings,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { api, type Health, type ModelsResponse, type PaperAccount } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { APP_NAME, TAGLINE } from "@/lib/brand";
import { LEVEL_TONE } from "@/lib/levels";
import { money } from "@/lib/format";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/strategy-desk", label: "Strategy Desk", icon: Sparkles },
  { href: "/backtest", label: "Backtest", icon: ChartLine },
  { href: "/paper-trading", label: "Paper Trading", icon: ClipboardList },
  { href: "/pnl", label: "Profit & Loss", icon: ChartColumn },
  { href: "/knowledge", label: "Knowledge Base", icon: BookOpen },
  { href: "/settings", label: "Settings & Models", icon: Settings },
];

function active(path: string, href: string): boolean {
  if (href === "/") return path === "/";
  if (href === "/backtest") return path.startsWith("/backtest") || path.startsWith("/results");
  return path.startsWith(href);
}

function SidebarNav() {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active(path, href)
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
            </Link>
          ))}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [dataName, setDataName] = useState<string | null>(null);
  const [paper, setPaper] = useState<PaperAccount | null>(null);

  // The paper balance in the sidebar: loaded once, then whenever the Paper Trading page changes the account.
  useEffect(() => {
    let on = true;
    const load = () => api.paperAccount().then((p) => on && setPaper(p)).catch(() => undefined);
    void load();
    window.addEventListener("paper-updated", load);
    return () => {
      on = false;
      window.removeEventListener("paper-updated", load);
    };
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOffline(true));
    api.models().then(setModels).catch(() => undefined);
    api.datasets().then((d) => setDataName(d[0]?.name ?? null)).catch(() => undefined);
  }, []);

  const ok = health?.status === "ok";
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-sidebar p-4 md:flex">
        <div className="px-2 pb-6 pt-2">
          <div className="text-lg font-semibold tracking-tight">{APP_NAME}</div>
          <div className="text-xs text-muted-foreground">{TAGLINE}</div>
        </div>
        <Suspense fallback={<nav className="flex flex-col gap-1" />}>
          <SidebarNav />
        </Suspense>
        <div className="mt-auto space-y-3 border-t px-2 pt-4 text-xs text-muted-foreground">
          {user && (
            <div>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-foreground" title={user.email}>{user.name}</span>
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium uppercase ${LEVEL_TONE[user.level]}`}>{user.level}</span>
              </div>
              <div className="truncate" title={user.email}>{user.email}</div>
              <button type="button" onClick={() => void signOut()} className="mt-1 text-primary hover:underline">
                Log out
              </button>
            </div>
          )}
          <Link href="/paper-trading" className="block rounded-lg bg-muted/60 px-2.5 py-2 hover:bg-muted">
            <div className="mb-0.5 text-[10px] uppercase tracking-wide">Paper account</div>
            <div className="font-mono text-sm font-semibold text-foreground">
              {paper ? money(paper.equity) : "–"}
            </div>
            <div className="text-[11px]">
              {paper ? `Virtual capital · cash ${money(paper.cash)}` : "Virtual capital"}
            </div>
          </Link>
          <div>
            <div className="mb-0.5 uppercase tracking-wide">Model</div>
            <div className="break-all font-mono text-foreground">{models?.default ?? "–"}</div>
            {models && !models.default_available && <div className="text-amber-600">provider not configured</div>}
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b bg-card px-6 py-2.5 text-xs">
          <div className="text-muted-foreground">
            <span className="font-semibold text-amber-700">Educational use</span> · Backtests only. No live orders
            are placed; you execute any trade yourself.
          </div>
          <div className="flex items-center gap-4 text-muted-foreground">
            <span>
              Data: <span className="font-medium text-foreground">{dataName ?? "none loaded"}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className={`size-2 rounded-full ${ok ? "bg-emerald-500" : offline ? "bg-red-500" : "bg-amber-400"}`}
              />
              API {ok ? "up" : offline ? "unreachable" : health ? "degraded" : "…"}
            </span>
          </div>
        </div>
        <div className="flex-1">{children}</div>
      </div>
    </div>
  );
}
