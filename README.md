# AI Powered Trading

A multi-agent system that turns a plain-English NIFTY / BANKNIFTY options idea into a verified strategy, a deterministic backtest,
and a trade plan.

> **Educational and research prototype.** No live trading, no broker integration, not financial advice.
> Backtests use historical data and simulated money only.

## What it does

Describe a trade in free text, for example *"BankNifty, capital 50k, max loss 2000, target 7777, EMA with RSI"*. The app then:

1. **Parses** the request (underlying, expiry, capital, max loss, target) and refuses anything outside NIFTY / BANKNIFTY options.
2. **Researches** the idea using a knowledge base (RAG) and recent market news.
3. **Builds a strategy** as a declarative JSON `StrategySpec`. No LLM-written code is ever executed.
4. **Verifies** the spec (fidelity to the idea, logic that can fire, risk settings) and sends it back for up to two revisions.
5. **Backtests** it on historical option candles with a pure Python engine.
6. **Reviews risk** and produces a trade plan with reasons. Lots, stop and target come from your rupee limits, computed in code.

You can also skip the AI and run a backtest directly from a template or spec.

## Core principle

LLMs never compute prices, signals, P&L, metrics, lots, rupees or stop/target percentages. Every number comes from deterministic
code in `backend/app/engine`. Agents only retrieve knowledge, translate intent into a spec, call the
engine as a tool, and explain the results.

## Features

- **Strategy Desk:** free-text trade request, live agent pipeline, trade plan with reasons.
- **Backtest engine:** signal on candle close, fill at the next candle open (no lookahead), stop/target/square-off, costs and slippage,
  metrics (P&L, win rate, profit factor, drawdown, Sharpe, expectancy) and a full trade log.
- **Profit & Loss page:** simulated P&L of your backtests after brokerage, slippage and taxes, for a day or a date range.
- **Accounts and experience levels:** beginner / advanced / expert tune explanations and add max-loss caps.
- **Model choice:** OpenAI, Anthropic, Gemini, Groq, Azure OpenAI, OpenRouter, Ollama, or an offline mock model.
- **Knowledge base:** upload `.md` / `.pdf` documents, embedded locally (no API key needed).
- **Guardrails:** input cleaning and injection blocking, scope gates, output checks, per-user budgets. See [`docs/guardrails.md`](docs/guardrails.md).
- **Optional tracing** with Langfuse; the app runs fine without it.

## Architecture

```
.
├── backend/    FastAPI + Postgres + ChromaDB (Docker Compose), Python 3.12, uv
│   └── app/    api, agents, engine, guardrails, rag, news, llm, data, schemas
├── frontend/   Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts
├── docs/       guardrails and longer guides
└── rag-data/   knowledge documents
```

Pipeline: `research -> strategy -> verify -> backtest -> risk review` (Pydantic AI agents, orchestrated in
`backend/app/agents/orchestrator.py`, each step saved to the run record).

## Quick start

Requirements: Docker with Compose, Node.js, and [uv](https://docs.astral.sh/uv/) for local backend tooling.

```bash
# 1. Backend (API on http://localhost:8000, docs at /docs)
cd backend
cp .env.example .env          # add at least one LLM key, or set ENABLE_MOCK_LLM=true and DEFAULT_MODEL=mock:demo
docker compose up --build

# 2. Frontend (http://localhost:3000)
cd ../frontend
cp .env.example .env.local
npm install
npm run dev
```

Load a dataset before backtesting: create a synthetic one with
`curl -X POST localhost:8000/datasets/synthetic -H 'content-type: application/json' -d '{}'`,
or import real NIFTY / BANKNIFTY data (see [`backend/README.md`](backend/README.md), "Datasets").
Local demo accounts can be created with `backend/otj/seed_users.py`; never use them on a shared server.

## Development

```bash
cd backend  && uv run pytest && uv run ruff check . && uv run mypy app
cd frontend && npm run lint && npm run build
cd frontend && npm run gen:api     # regenerate API types (backend must be running)
```

## Documentation

- [`PROJECT_SPEC.md`](PROJECT_SPEC.md): original specification
- [`backend/README.md`](backend/README.md): API, engine, agents, RAG, data import, env vars
- [`frontend/README.md`](frontend/README.md): pages and setup
- [`docs/guardrails.md`](docs/guardrails.md): safety layers, OWASP mapping, measured results and known gaps
- [`CLAUDE.md`](CLAUDE.md): guidance for Claude Code (project rules, commands, subagents)

## Disclaimer

This software is for education and research only. It does not provide investment advice, and nothing it outputs is a recommendation
to buy or sell any security. Options trading carries substantial risk of loss.
