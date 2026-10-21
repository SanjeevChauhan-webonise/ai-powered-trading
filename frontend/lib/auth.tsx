"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, type TokenOut, type User } from "./api";
import { clearToken, getToken, setToken } from "./token";

interface AuthState {
  user: User | null;
  ready: boolean; // false until the stored login has been checked
  signIn: (res: TokenOut) => void;
  signOut: () => Promise<void>;
  setUser: (u: User) => void;
}

const Ctx = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let on = true;
    const stored = getToken();
    (stored ? api.me().then((u) => on && setUser(u)) : Promise.resolve())
      .catch(() => clearToken())
      .finally(() => on && setReady(true));
    return () => {
      on = false;
    };
  }, []);

  const signIn = useCallback((res: TokenOut) => {
    setToken(res.token);
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    clearToken();
    setUser(null);
    router.replace("/login");
  }, [router]);

  const value = useMemo(() => ({ user, ready, signIn, signOut, setUser }), [user, ready, signIn, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Renders its children only for a logged-in user; everyone else is sent to /login. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);
  if (!ready || !user) return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;
  return <>{children}</>;
}
