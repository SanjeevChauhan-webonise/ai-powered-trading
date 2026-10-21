import { money } from "@/lib/format";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{message}</p>;
}

export function PnlText({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  const tone = value == null ? "" : value > 0 ? "text-emerald-700" : value < 0 ? "text-red-700" : "";
  return (
    <span className={`font-mono ${tone} ${className}`}>
      {value != null && value > 0 ? "+" : ""}
      {money(value)}
    </span>
  );
}
