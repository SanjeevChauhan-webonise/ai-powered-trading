# Frontend

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts. Educational use only.

```bash
cp .env.example .env.local   # sets NEXT_PUBLIC_API_URL
npm install
npm run dev                  # http://localhost:3000
npm run lint
```

The backend must be running (`cd ../backend && docker compose up`).

## Pages
Every page except `/login` needs a login (token kept in the browser's localStorage, sent as a Bearer header; a 401 sends you back
to `/login`). `/login` also creates accounts and shows the fake demo accounts unless `NEXT_PUBLIC_DEMO_LOGINS=false`.
Sidebar layout (`components/layout/app-shell.tsx`), design from "Strategy Desk (AI query)".
- `/`: dashboard. Counts, recent AI runs (open one in the Strategy Desk), recent backtests, datasets.
- `/strategy-desk`: describe a trade in free text, pick underlying / expiry (dropdown of upcoming expiries estimated from the usual weekday, `lib/expiries.ts`) / capital / max loss / target / risk appetite, and
  get a trade plan with reasons plus the live agent pipeline. Calls `POST /runs/parse`, then `POST /runs`, and polls `GET /runs/{id}`.
  `?run=<id>` reopens an earlier run. A general options question ("what is theta decay?") is answered directly (knowledge base and news, no plan,
  no backtest); anything outside NIFTY / BANKNIFTY options trading is refused with a short message. Lots, stop and target come from your rupee limits (computed in the backend, not by the LLM).
- `/backtest`: all backtests. `/backtest/new`: pick dataset + template, run a direct (no-AI) backtest.
- `/results/[id]`: metrics, equity / drawdown / daily P&L charts, sortable + filterable trade log.
- `/pnl`: Profit & Loss for a **day or a date range** (presets All / Last day / Last 7 days / Last 30 days, or From and To dates; the same
  date twice is one day). It shows the simulated P&L of your backtests, filtered by the day each backtest was run.
  Simulated money only.
- `/knowledge`: browse, search, upload (`.md` / `.pdf`) and re-ingest the RAG knowledge base.
- `/settings`: your profile and experience level (beginner / advanced / expert), available models, default model, service status.
- `/login`: log in or create an account.

FINNIFTY / MIDCPNIFTY are shown disabled in the Strategy Desk (the backend supports NIFTY and BANKNIFTY).

## API types
`lib/api-types.ts` is generated from the backend OpenAPI schema. With the backend running:
```bash
npm run gen:api
```
Re-run it whenever backend request/response models change.
