import { redirect } from "next/navigation";

import { SHOW_PAPER_TRADING } from "@/lib/features";

export default function PaperTradingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  if (!SHOW_PAPER_TRADING) redirect("/");
  return children;
}
