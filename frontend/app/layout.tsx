import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Options Strategy Backtester",
  description: "Educational options strategy backtesting research prototype",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3 text-sm">
            <Link href="/" className="font-semibold">
              Options Backtester
            </Link>
            <Link href="/backtest/new" className="text-muted-foreground hover:text-foreground">
              New backtest
            </Link>
          </nav>
        </header>
        <div className="flex-1">{children}</div>
        <footer className="border-t px-6 py-3 text-center text-xs text-muted-foreground">
          Educational/research use only. Not financial advice. No live trading.
        </footer>
      </body>
    </html>
  );
}
