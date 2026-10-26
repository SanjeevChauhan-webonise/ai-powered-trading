# AI Powered Trading

Multi-agent system that turns a plain-English NIFTY / BANKNIFTY options idea into a verified strategy, a deterministic backtest,
and a trade plan. Educational use only: no live trading, no broker orders, not financial advice.
Original spec: `PROJECT_SPEC.md`. Guardrails: `docs/guardrails.md`. Longer guides (.docx/.pdf) are in `docs/`.

## Repo layout
- `backend/` FastAPI + Postgres + ChromaDB, Python 3.12, uv, runs via Docker Compose. See `backend/CLAUDE.md`.
- `frontend/` Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts. See `frontend/CLAUDE.md`.
- `.claude/agents/` project subagents (see below).

## Core principle (never break)
LLMs never compute prices, signals, P&L, metrics, lots, rupees or stop/target %. All numbers come from deterministic Python in
`backend/app/engine`. Agents only retrieve knowledge, translate intent into a `StrategySpec`, call the engine
as a tool, and explain results. Strategies are declarative JSON (`app/schemas/strategy.py`); never execute user- or LLM-written code.

## Pipeline (backend/app/agents/orchestrator.py)
research (RAG + market news) -> strategy -> verify (up to 2 revision rounds) -> backtest -> risk review. Extra agents: intake
(parses a free-text trade request, flags off-topic) and ask (answers general options questions). Each step is persisted to the
`pipeline_runs` row; the frontend polls `GET /runs/{id}`.

## Domain rules
- Scope: NIFTY and BANKNIFTY options only. Off-topic requests are refused (intake `intent=off_topic`, ask `in_scope=false`).
- Backtest: signal on candle close, fill at next candle open (no lookahead). Stop wins over target when both are reachable in one
  candle. Intraday only, 15:15 square-off. Bullish buys CE, bearish buys PE (sell direction flips this).
- Users have experience levels (beginner / advanced / expert) that tune explanations and add max-loss caps (5% / 10% / 25% of capital).
- Data is per user (`user_id`); other users get 404. Datasets, knowledge base and models are shared.
- Timestamps are naive exchange-local time (Asia/Kolkata). Lot sizes change over time; use `app/engine/lots.py`.

## Commands
- Stack: `cd backend && cp .env.example .env && docker compose up --build` (API on :8000, docs at /docs, ChromaDB host port 8001).
- Backend check: `cd backend && uv run pytest && uv run ruff check . && uv run mypy app`
- Frontend: `cd frontend && npm run dev | npm run lint | npm run build | npm run gen:api` (gen:api needs the backend running).
- Prompt/guard eval (costs a few cents, needs a running API): `cd backend && MODEL=openai:gpt-4o-mini PYTHONPATH=. uv run python otj/eval_prompts.py`
- Offline demo without API keys: `ENABLE_MOCK_LLM=true` and `DEFAULT_MODEL=mock:demo`.

## Conventions
- Ruff line length 120 (rules E, F, I, UP, B), mypy strict with the pydantic plugin. Keep code simple, typed, readable.
- Every behavior change gets a test in `backend/tests`. Do not add major dependencies without asking.
- Never commit `.env`, API tokens, `backend/option-data/`, or `backend/storage/` contents. Fake test accounts (`otj/accounts.py`,
  password `Test@12345`) are for local use only.
- Write code, comments and docs in English.

## Subagents (`.claude/agents/`)
- `backend-dev`: API, schemas, migrations, RAG, LLM registry.
- `engine-reviewer`: read-only review of backtest engine for lookahead, determinism and cost correctness.
- `guardrail-reviewer`: read-only review of prompts, guardrails and anything LLM-facing.
- `frontend-dev`: Next.js pages, components, API client and types.
- `data-ops`: TheTrade conversion and CSV dataset loading scripts in `backend/otj`, dataset validation.
