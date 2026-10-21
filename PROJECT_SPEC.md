# Project: AI-Powered Options Strategy Backtesting System

## Goal
Build a multi-agent AI system that researches, defines, backtests and reviews
trading strategies on historical options data (any underlying: NIFTY, BANKNIFTY,
FINNIFTY, stock options). Educational/research prototype only: NO live trading,
NO broker integration, NO authentication.

## Working style (important)
- Before writing code, read this spec fully and propose a plan for the current
  phase. Wait for my approval, then implement.
- Work phase by phase (see "Phases"). At the end of each phase: run tests,
  make sure `docker compose up` works, summarize what was done, then stop.
- Ask me before adding major dependencies or deviating from this spec.
- Keep code simple, typed, and readable. No over-engineering.

## Architecture
Monorepo with two independent parts:

```
repo/
├── backend/            # runs fully via docker compose
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── .env.example
│   └── app/
│       ├── api/        # FastAPI routers
│       ├── core/       # config (pydantic-settings), logging, db
│       ├── data/       # dataset ingestion, normalization, storage
│       ├── engine/     # indicators, strategy evaluator, backtester, metrics
│       ├── agents/     # research, strategy, backtest, risk, orchestrator
│       ├── rag/        # ingestion, retriever, knowledge docs (markdown)
│       ├── llm/        # model registry / provider abstraction
│       └── schemas/    # all Pydantic models
└── frontend/           # Next.js app, run separately with npm (NOT in compose)
```

### Backend (docker compose)
Services:
- `api`: FastAPI (Python 3.12, uv or pip), hot reload in dev via volume mount
- `postgres`: stores datasets metadata, strategies, backtest runs and results
- `chromadb`: vector store for RAG (persistent volume)
Langfuse: use Langfuse Cloud via env keys by default. Tracing must be optional;
the app must run fine if Langfuse keys are missing.
Raw/normalized market data stored as Parquet files in a mounted volume
(`./storage`), not in Postgres.
Enable CORS for the frontend origin (configurable via env). No auth anywhere.

### Frontend (separate)
- Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts
- Backend URL from `NEXT_PUBLIC_API_URL`
- Runs with `npm run dev`, has its own README

## Core Principle
LLMs NEVER compute prices, signals, P&L or metrics. All backtesting is
deterministic Python/Pandas code. Agents only: retrieve knowledge, translate
user intent into a structured strategy spec, call the engine as a tool, and
explain/review results.

## 1. Data Layer (generic, any options data)
- Upload CSV or Parquet via API. User provides a column mapping so any
  source format works.
- Normalize to a standard schema:
  - Underlying candles: `timestamp, symbol, open, high, low, close, volume`
  - Option candles: `timestamp, underlying, expiry, strike, option_type (CE/PE),
    open, high, low, close, volume, oi (optional)`
- Support any timeframe; allow resampling (e.g. 1min -> 5min, 15min).
- Store per-dataset metadata: underlying, date range, timeframe, lot size,
  available expiries/strikes.
- Validation: report missing candles, duplicates, gaps, bad timestamps.
- Include a synthetic data generator script (realistic-looking underlying +
  option chain) so the whole system can be tested without real data.

## 2. Strategy Definition (declarative, NOT arbitrary code)
Strategies are JSON specs validated by Pydantic. Never execute user- or
LLM-generated Python code.

`StrategySpec` should support:
- Signal source: underlying candles (default) or option candles
- Indicators: EMA, SMA, RSI, MACD, Bollinger Bands, ATR, VWAP, SuperTrend
  (registry pattern so adding new ones is easy)
- Entry/exit conditions: composable rules (crosses_above, crosses_below,
  >, <, between) combined with AND/OR
- Instrument selection: CE/PE/both, strike selection (ATM, ATM±N strikes,
  nearest premium to X), expiry selection (nearest weekly, monthly)
- Direction: buy or sell options
- Risk rules: stop loss %, target %, trailing SL, max trades per day,
  time window for entries, forced intraday square-off time
- Position sizing: number of lots
- Costs: brokerage per order, slippage (points or %), taxes approximation

Ship built-in templates: EMA Crossover and RSI Reversal (both producing CE on
bullish signal, PE on bearish signal).

## 3. Backtest Engine
- No lookahead bias: signal on candle close, entry at next candle open.
- Handle expiry rollover and missing option candles gracefully (skip + log).
- Output: trade log (entry/exit time, instrument, prices, qty, P&L, exit reason),
  equity curve, and metrics: total P&L, win rate, avg win/loss, profit factor,
  max drawdown (abs and %), Sharpe ratio, number of trades, expectancy,
  best/worst trade, daily P&L breakdown.
- Must be pure and unit-testable (no LLM, no DB inside the engine).

## 4. LLM Layer (any model)
- Use Pydantic AI with model strings, provider-agnostic: OpenAI, Anthropic,
  Google Gemini, Groq, OpenRouter, Ollama (local).
- A model registry reads which providers have API keys in env and exposes
  available models via `GET /models`.
- Model can be chosen per request (and optionally per agent), with a default
  from env.
- Embeddings configurable; default to a local sentence-transformers model so
  RAG works without any API key.

## 5. RAG Knowledge Base
- Markdown docs in `app/rag/docs/`: indicators, options basics, Greeks,
  risk management, each built-in strategy. Write solid starter docs yourself.
- Chunk, embed, store in ChromaDB. Re-ingest endpoint.
- Allow uploading extra markdown/PDF docs via API.
- Retriever returns chunks with source metadata.

## 6. Agents (Pydantic AI)
Each agent has a clear system prompt and a typed output:
1. Research Agent: tool `search_knowledge`; outputs relevant concepts and
   considerations for the user's idea.
2. Strategy Agent: converts natural language (e.g. "buy ATM CE when 9 EMA
   crosses 21 EMA on 5min, SL 20%") OR a template into a valid `StrategySpec`.
   If validation fails, retry with the error message.
3. Backtest Agent: tool `run_backtest(spec, dataset_id, date_range)` calling
   the deterministic engine.
4. Risk Review Agent: reads metrics + trade log summary; outputs strengths,
   weaknesses, red flags (too few trades, overfitting risk, high drawdown,
   cost sensitivity) and suggestions.
Orchestrator: simple async pipeline running these in sequence, persisting each
step's output to the run record. Stream progress to the frontend (SSE).
Users can also skip AI entirely and run a backtest directly from a spec.

## 7. Observability
- Instrument Pydantic AI with OpenTelemetry → Langfuse (agent runs, prompts,
  tool calls, tokens, latency, errors). Tag traces with run_id.
- Structured logging in the app.

## 8. API (FastAPI)
- `POST /datasets/upload`, `GET /datasets`, `GET /datasets/{id}`
- `GET /strategies/templates`, `POST /strategies`, `GET /strategies`,
  `POST /strategies/validate`
- `POST /strategies/from-text` (Strategy Agent only)
- `POST /backtests` (direct, no AI), `GET /backtests/{id}`, `GET /backtests`
- `POST /runs` (full multi-agent pipeline), `GET /runs/{id}`,
  `GET /runs/{id}/stream` (SSE)
- `GET /models`, `POST /knowledge/ingest`, `GET /health`
OpenAPI docs must be clean so I can generate frontend types from them.

## 9. Frontend Pages
- Datasets: upload, column mapping wizard, dataset details and quality report
- Strategy Builder: pick a template, or form-based rule builder, or describe in
  plain English (AI) → show the generated spec, editable
- Run: choose dataset, date range, strategy, model → live agent progress
- Results: metric cards, equity curve, drawdown chart, daily P&L chart,
  trade log table (sortable/filterable), AI research + risk review
- History: past runs, compare 2–3 runs side by side
- Clear disclaimer: educational only, not financial advice

## 10. Quality
- pytest for engine (indicators against known values, no-lookahead test,
  SL/target/square-off logic, metrics), data normalization, spec validation.
- Ruff + mypy for backend, ESLint for frontend.
- READMEs: setup, env vars, how to add a new indicator / data source / model.

## Phases
- Phase 0: repo skeleton, docker compose (api + postgres + chromadb), health
  endpoint, config, frontend skeleton calling /health
- Phase 1: data layer + synthetic data generator
- Phase 2: StrategySpec + indicators + backtest engine + metrics + tests
- Phase 3: direct backtest API + frontend results page
- Phase 4: LLM model registry + RAG
- Phase 5: agents + orchestrator + SSE + Langfuse
- Phase 6: remaining frontend pages (builder, history, compare) + polish