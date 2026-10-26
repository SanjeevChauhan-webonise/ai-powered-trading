/** Date helpers on ISO "YYYY-MM-DD" strings (no time zones involved). */
export const addDays = (iso: string, n: number): string => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export const isoDay = (stamp: string): string => stamp.slice(0, 10);

export const dayLabel = (iso: string): string =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

export const clampDate = (iso: string, min: string | null, max: string | null): string =>
  min && iso < min ? min : max && iso > max ? max : iso;

export interface Range {
  from: string; // "" = from the beginning
  to: string; // "" = up to the end
}
export const ALL: Range = { from: "", to: "" };
