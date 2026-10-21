/**
 * Upcoming option expiries for the dropdown, computed from the exchange's usual weekday (the backend has no
 * live contract list). An exchange holiday can move an expiry to the previous trading day, so the UI says to
 * confirm the date in your broker. Edit RULES if NSE changes the weekday or the weekly contracts.
 */
export interface ExpiryOption {
  date: string; // YYYY-MM-DD
  kind: "weekly" | "monthly";
  days: number;
}

const RULES: Record<string, { weekday: number; weekly: boolean; note: string }> = {
  NIFTY: { weekday: 2, weekly: true, note: "NIFTY has weekly (Tue) and monthly (last Tue) expiries" },
  BANKNIFTY: { weekday: 2, weekly: false, note: "BANKNIFTY has monthly expiries only (last Tue)" },
};

const iso = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const expiryNote = (underlying: string | null): string => (underlying && RULES[underlying]?.note) || "";

/** Weekly vs monthly the way the backend decides: the last expiry of a month is the monthly one. */
export function expiryKind(date: string): "weekly" | "monthly" {
  const d = new Date(`${date}T00:00:00`);
  return new Date(d.getTime() + 7 * 864e5).getMonth() !== d.getMonth() ? "monthly" : "weekly";
}

export function daysTo(date: string, today = new Date()): number {
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((new Date(`${date}T00:00:00`).getTime() - t.getTime()) / 864e5);
}

export function upcomingExpiries(underlying: string | null, count = 8, today = new Date()): ExpiryOption[] {
  const rule = underlying ? RULES[underlying] : undefined;
  if (!rule) return [];
  const out: ExpiryOption[] = [];
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  for (let i = 0; i < 400 && out.length < count; i++, d.setDate(d.getDate() + 1)) {
    if (d.getDay() !== rule.weekday) continue;
    const date = iso(d);
    const kind = expiryKind(date);
    if (kind === "weekly" && !rule.weekly) continue;
    out.push({ date, kind, days: daysTo(date, today) });
  }
  return out;
}

export function expiryLabel(o: ExpiryOption): string {
  const when = new Date(`${o.date}T00:00:00`).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const left = o.days === 0 ? "today" : o.days < 0 ? "past" : `${o.days}d`;
  return `${when} · ${o.kind === "monthly" ? "Monthly" : "Weekly"} · ${left}`;
}
