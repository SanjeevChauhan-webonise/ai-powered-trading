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
- `/backtest/new`: pick dataset + template, optional date range and capital, run a direct (no-AI) backtest.
- `/results/[id]`: metrics, equity / drawdown / daily P&L charts, sortable + filterable trade log.

## API types
`lib/api-types.ts` is generated from the backend OpenAPI schema. With the backend running:
```bash
npm run gen:api
```
Re-run it whenever backend request/response models change.
