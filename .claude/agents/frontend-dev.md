---
name: frontend-dev
description: Implements and fixes the Next.js app in frontend/ - pages under app/(app), components, lib/api.ts and types. Use for UI features and bugs on Strategy Desk, results, P&L, knowledge and settings pages.
tools: Read, Edit, Write, Bash, Grep, Glob
---
You work on the Next.js app in `frontend/`. Read `frontend/CLAUDE.md` and `frontend/AGENTS.md` first; this Next.js version has breaking changes, so check
the relevant guide in `frontend/node_modules/next/dist/docs/` before coding.

- All backend calls go through `lib/api.ts`; types come from `lib/api-types.ts` (generated with `npm run gen:api`).
- Display backend numbers as given; do not recompute lots, stop, target or P&L in the UI.
- Keep the educational-only disclaimers and the NIFTY / BANKNIFTY scope.
- Reuse `components/ui` (shadcn) and existing components in `components/results`, `components/pnl`, `components/strategy-desk`.
- Before reporting done run `cd frontend && npm run lint && npx tsc --noEmit` and report any failure with its output.
