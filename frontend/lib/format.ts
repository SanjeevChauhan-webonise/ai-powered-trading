const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export const money = (n: number | null | undefined): string =>
  n == null ? "–" : `${n < 0 ? "-" : ""}₹${inr.format(Math.abs(n))}`;

export const num = (n: number | null | undefined, digits = 2): string =>
  n == null ? "–" : n.toFixed(digits);

export const pct = (n: number | null | undefined, digits = 1): string =>
  n == null ? "–" : `${n.toFixed(digits)}%`;

export const shortDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short" });

export const dateTime = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
