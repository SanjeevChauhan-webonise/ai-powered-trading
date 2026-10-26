"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addDays, ALL, clampDate, dayLabel, type Range } from "@/lib/dates";

const label = "mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

/** Pick one day (From = To), a range, or a preset. Presets are counted back from the latest date that has data. */
export function DateRange({
  value,
  onChange,
  min,
  max,
}: {
  value: Range;
  onChange: (r: Range) => void;
  min: string | null; // first date with data
  max: string | null; // last date with data
}) {
  const disabled = !min || !max;
  const presets: { name: string; range: Range }[] = [
    { name: "All", range: ALL },
    { name: "Last day", range: { from: max ?? "", to: max ?? "" } },
    { name: "Last 7 days", range: { from: max ? clampDate(addDays(max, -6), min, max) : "", to: max ?? "" } },
    { name: "Last 30 days", range: { from: max ? clampDate(addDays(max, -29), min, max) : "", to: max ?? "" } },
  ];
  const active = (r: Range) => r.from === value.from && r.to === value.to;
  const set = (patch: Partial<Range>) => {
    const next = { ...value, ...patch };
    if (next.from && next.to && next.from > next.to) {
      // keep it valid: the date that was just edited wins and the other one follows it
      if (patch.from !== undefined) next.to = next.from;
      else next.from = next.to;
    }
    onChange(next);
  };

  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-xl border bg-card p-4">
      <div>
        <div className={label}>Period</div>
        <div className="flex flex-wrap gap-1.5">
          {presets.map((p) => (
            <Button key={p.name} size="sm" variant={active(p.range) ? "default" : "outline"} disabled={disabled && p.name !== "All"} onClick={() => onChange(p.range)}>
              {p.name}
            </Button>
          ))}
        </div>
      </div>
      <div>
        <label className={label} htmlFor="from">From</label>
        <Input id="from" type="date" className="h-8 w-40 bg-background" min={min ?? undefined} max={value.to || max || undefined} value={value.from} disabled={disabled} onChange={(e) => set({ from: e.target.value })} />
      </div>
      <div>
        <label className={label} htmlFor="to">To</label>
        <Input id="to" type="date" className="h-8 w-40 bg-background" min={value.from || min || undefined} max={max ?? undefined} value={value.to} disabled={disabled} onChange={(e) => set({ to: e.target.value })} />
      </div>
      <p className="pb-1 text-xs text-muted-foreground">
        {disabled
          ? "No dated trades yet."
          : value.from && value.from === value.to
            ? `Single day: ${dayLabel(value.from)}`
            : value.from || value.to
              ? `${value.from ? dayLabel(value.from) : "start"} to ${value.to ? dayLabel(value.to) : "end"}`
              : `All time (${dayLabel(min!)} to ${dayLabel(max!)}). Set both dates the same for one day.`}
      </p>
    </div>
  );
}
