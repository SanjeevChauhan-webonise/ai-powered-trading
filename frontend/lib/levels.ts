import type { Level } from "./api";

export const LEVELS: { id: Level; label: string; blurb: string }[] = [
  {
    id: "beginner",
    label: "Beginner",
    blurb: "Plain words, simple strategies, conservative limits (max 3 trades a day, risk above 2% of capital is flagged).",
  },
  {
    id: "advanced",
    label: "Advanced",
    blurb: "Standard depth. Combinations of a few indicators, short trade-offs, risk above 5% of capital is flagged.",
  },
  {
    id: "expert",
    label: "Expert",
    blurb: "Concise and technical, no basics. Risk above 10% of capital is flagged.",
  },
];

export const LEVEL_TONE: Record<Level, string> = {
  beginner: "bg-emerald-100 text-emerald-800",
  advanced: "bg-blue-100 text-blue-800",
  expert: "bg-violet-100 text-violet-800",
};
