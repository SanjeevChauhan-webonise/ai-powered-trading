# Backend

FastAPI + Postgres + ChromaDB, run via Docker Compose. Educational use only; not financial advice.

## Setup
```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/health      # docs at /docs
```

## Local dev tooling
```bash
uv sync
uv run pytest && uv run ruff check . && uv run mypy app
```

## Env vars
See `.env.example`. Langfuse keys are optional; the app runs without them. `UPSTOX_ACCESS_TOKEN` is only needed for the Upstox import (below).

## Guardrails (scope, safety, budgets)
The app only works for NIFTY / BANKNIFTY options trading. Full explanation, the OWASP mapping, measured results and the gaps are in
[`docs/guardrails.md`](../docs/guardrails.md). In short, several independent layers, the important ones in code outside the model:
- **Input guard** (`app/guardrails/text.py`): cleans text, blocks prompt-injection phrases **before any model call**, redacts email,
  PAN, Aadhaar, phone, card numbers and API keys.
- **Prompts** (`app/agents/prompts.py`): one shared `<scope>` block (what is in scope, refusal protocol, outside text is data) in all seven agents.
- **Scope gates in code:** intake `intent=off_topic`, ask `in_scope=false`, and the research step stops a run on an off-topic idea.
- **Data filters:** news items and knowledge passages that look like injection are dropped before an agent reads them.
- **Output guards** (`app/guardrails/output.py`): no promises of profit, no direct buy/sell orders, and the strategy text may not quote
  lots, rupees or stop/target % (a violation makes the agent rewrite).
- **Budgets** (`app/guardrails/limits.py`, `.env`): `LLM_CALLS_PER_MINUTE=12`, `MAX_ACTIVE_RUNS_PER_USER=2`, `RUNS_PER_DAY=40` (HTTP 429), and a
  hard cap on max loss per trade of 5% / 10% / 25% of capital for Beginner / Advanced / Expert.
- **Check it:** `MODEL=openai:gpt-4o-mini PYTHONPATH=. uv run python otj/eval_prompts.py` runs a fixed set of in-scope, off-topic, injection and
  vague requests against the running API (a few cents). Run it after any prompt or guard change.

## Accounts and experience levels
Email + password accounts (`app/api/auth.py`, `app/core/security.py`). Everything except `/health` and `/auth/*` needs
`Authorization: Bearer <token>`.
- `POST /auth/register` (`email`, `name`, `password` of 8+ chars, `level`), `POST /auth/login`, `GET /auth/me`, `PATCH /auth/me`
  (name, level), `POST /auth/logout`, `POST /auth/change-password` (ends your other logins). `ALLOW_REGISTRATION=false` closes sign-up.
- Passwords are hashed with scrypt (standard library). A login is an opaque random token; only its SHA-256 is stored
  (`auth_sessions`), it expires after `AUTH_SESSION_HOURS` (default 168) and logout deletes it. Failed logins are limited per
  email (in memory, resets on restart). Login errors never say whether the email exists.
- **Data scope:** strategies, backtests and AI runs belong to the user who made them (`user_id`); other users get 404.
  Datasets, the knowledge base and models are shared.
- **Levels** `beginner | advanced | expert` (set at sign-up, change with `PATCH /auth/me` or Settings) tune the agents'
  explanations and add code guardrails: a risk note when max loss per trade is above 2% / 5% / 10% of capital, and for beginners
  at most 3 trades a day. Numbers still come only from code.
- Migration `0004` adds `users`, `auth_sessions`, `level` and the `user_id` columns (existing rows start unowned).

**Fake test accounts** (`otj/accounts.py`, same password for all, never use on a shared server):
the owner (your own email from `OWNER_EMAIL` in `backend/.env`, default `owner@example.com`; advanced), `amit@example.com` (beginner), `priya@example.com` (advanced),
`rahul@example.com` (expert), `sneha@example.com` (beginner); password `Test@12345`.
```bash
docker compose exec api alembic upgrade head      # if the container did not already apply 0004
docker compose run --rm -e PYTHONPATH=/app -v "$PWD/otj:/app/otj" api python otj/seed_users.py
PYTHONPATH=. uv run python otj/fake_users.py      # each persona logs in and runs its own query
```
`seed_users.py` also hands runs that existed before accounts (tagged "[Amit]" etc. go to that persona, the rest to
`ADOPT_UNOWNED_TO`) to their owners. Change the default passwords (`POST /auth/change-password`) for any account you keep.

## Paper trading (simulation on replayed data)
Each user has one paper account (`paper_accounts`, default balance Rs 5,00,000) with `paper_positions`, `paper_orders` and
`paper_trades`. There is **no live feed**: the "market" is a loaded dataset replayed by a **market clock** (`app/paper/`).
- `POST /paper/clock/start {dataset_id}` picks the dataset and starts the clock (first candle of the 3rd-last day), and
  `POST /paper/clock/advance {candles}` moves it forward. Orders fill at the price of the candle the clock is on.
- `GET /paper/expiries`, `GET /paper/chain?expiry=` (only expiries that have prices at the market time),
  `POST /paper/orders` (buy), `POST /paper/positions/{id}/close` (sell to close), `GET /paper/account|positions|orders|trades`,
  `POST /paper/account/reset`, and `POST /paper/from-plan {run_id, option_type}` to paper-trade an AI trade plan (same lots,
  stop, target and 15:15 square-off; the strike follows the plan's ATM / offset / nearest-premium rule).
- Positions are long options only (selling to open is rejected). While the clock advances, each candle runs the exits:
  expiry, stop loss, target and square-off. Costs are charged when a trade closes (2 x Rs 20 brokerage + 0.05% taxes, the backtest
  engine's defaults), so cash always moves by exactly the trade's net P&L.
- `GET /paper/pnl?date_from=&date_to=` is the realised P&L of closed trades for a day (both dates the same) or a range: net / gross /
  costs, win rate, profit factor, average win and loss, best and worst trade, max drawdown, a daily series with the running total, and
  breakdowns by exit reason and CE/PE. The bounds of the account's trades come back too. `GET /paper/trades` takes the same
  `date_from` / `date_to`. Dates are market-clock days (the day the trade was closed); unrealised P&L is not included.
- Everything is private to the user. Migration `0005` adds the tables.
- Fake history for the five test accounts (orders, closed trades, open positions), made by replaying the data with this same code:
```bash
docker compose exec api alembic upgrade head
docker compose run --rm -e PYTHONPATH=/app -v "$PWD/otj:/app/otj" api python otj/seed_paper.py   # RESETS those accounts first
```

## Datasets (Phase 1)
A dataset holds underlying candles and/or option candles, stored as Parquet in `./storage/<id>/`
(metadata in Postgres; migrations run automatically on container start).

```bash
# one-call demo dataset (NIFTY-like, 20 days, 1-min, ~1M option rows)
curl -X POST localhost:8000/datasets/synthetic -H 'content-type: application/json' -d '{}'

# upload your own: `mapping` maps standard field -> your column name
curl -F file=@u.csv -F kind=underlying -F underlying=NIFTY -F lot_size=75 \
  -F 'mapping={"timestamp":"Time","open":"O","high":"H","low":"L","close":"C","volume":"V"}' \
  localhost:8000/datasets/upload
# add options to the same dataset with kind=options and dataset_id=<id>
# optional: -F resample_to=5 to store 5-min candles
```
Timestamps are stored as naive exchange-local time (naive inputs are assumed to be in the mapping's
`timezone`, default Asia/Kolkata). Invalid rows are dropped and reported in the quality report.

### Real NIFTY / BANKNIFTY data from Upstox
Two scripts in `otj/` (settings are edited inside each file, in the `SETTINGS` block at the top):

1. **`otj/export_upstox_csv.py`** downloads history from Upstox into CSV files.
2. **`otj/load_csv_to_db.py`** loads those CSVs into the database as one dataset per underlying.

```bash
cd backend
export UPSTOX_ACCESS_TOKEN=...                      # Upstox Analytics Token (no daily re-login)
# 1. edit SETTINGS in otj/export_upstox_csv.py, then:
PYTHONPATH=. uv run python otj/export_upstox_csv.py
# 2. edit SETTINGS in otj/load_csv_to_db.py (lot sizes!), then:
PYTHONPATH=. uv run python otj/load_csv_to_db.py     # docker: docker compose exec api python otj/load_csv_to_db.py
```
The loader prints each dataset `id`; use it as `dataset_id` in `POST /backtests`.

Export settings: `UNDERLYINGS` (NIFTY, BANKNIFTY), `START`/`END`, `INTERVAL_MINUTES` (1, 3, 5, 15, 30),
`INCLUDE_OPTIONS`, `OPTION_TYPES` (CE/PE), `EXPIRY_TYPE` (all/weekly/monthly), `LAST_EXPIRIES` (most recent N),
`N_STRIKES` (each side of ATM). Output goes to `option-data/<UNDERLYING>/<N>m/`: `underlying.csv` plus one
`options_<expiry>.csv` per expiry (gitignored). Re-running skips files that already exist, so an interrupted export resumes.

Limits to know about:
- Underlying minute candles go back to Jan 2022. Option candles come from Upstox's expired-instruments API: it needs an
  **Upstox Plus** plan and lists only about the last 6 months of expiries.
- Requests are throttled and retried (Upstox allows 2000 calls per 30 min), so 1-minute option exports of many
  expiries take hours. Start with a short range.
- Lot sizes in `otj/load_csv_to_db.py` are defaults; they change over time, so check the current NSE value.
- These scripts have only been tested against mocked Upstox responses, not the live API.

Without scripts, the API offers the same: `POST /datasets/upstox` (small imports, runs inside the request) and
`POST /datasets/upstox/export-jobs` (background CSV export to `storage/exports/`; poll `GET /datasets/upstox/export-jobs/{id}`).

Generate files without the API: `uv run python -m app.data.synthetic --out-dir storage/synthetic --format csv`

## Strategy engine (Phase 2)
- `app/schemas/strategy.py`: `StrategySpec`, a declarative JSON spec. Code is never executed. Templates: `app/engine/templates.py`.
- `app/engine/backtest.py`: `run_backtest(spec, underlying_df, options_df, lot_size=..., start=, end=, capital=)`. Pure function.
  Signal on candle close, fill at the next candle's open. Stop wins over target if both are reachable in one candle.
  Bullish signal buys CE (sell direction: sells PE); bearish buys PE (sells CE). Positions are intraday.
  `gross_pnl` uses slippage-adjusted fills; `net_pnl = gross - brokerage - taxes`. `signal_source: option` is not supported yet.
- Metrics: realised-equity drawdown (per trade close); Sharpe = daily net P&L / capital over all trading days, rf=0, x sqrt(252).
- Smoke run: `PYTHONPATH=. uv run python scripts/smoke_backtest.py`

### Add an indicator
In `app/engine/indicators.py`:
```python
@register("my_ind", {"period": 10}, ("value",))  # name, default params, output columns
def my_ind(df: pd.DataFrame, p: Params) -> pd.DataFrame: ...
```
Then add the name to `IndicatorType` in `app/schemas/strategy.py`. Must be causal (row t uses rows <= t); the
parametrized no-lookahead test in `tests/test_indicators.py` covers every registered indicator automatically.

## LLM models (Phase 4)
`GET /models` lists models from providers whose credentials are set in env (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENTS` (model ids are `azure:<deployment>`), `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`). Model ids are `provider:model`, e.g.
`anthropic:claude-sonnet-5-5`. A request can pick any model; otherwise `<AGENT>_MODEL` (research / strategy / verify / backtest / risk)
then `DEFAULT_MODEL` applies (`app/llm/registry.py: resolve_model`, `build_model`).

**Add a model:** append it to the provider's tuple in `app/llm/registry.py`, or set `EXTRA_MODELS=openai:some-new-model` in env.
Any model name works for requests even if unlisted; only the provider must be configured.
**Add a provider:** add a `Provider(...)` row, a Settings field for its key, and a `case` in `build_model`.

## Knowledge base / RAG (Phase 4)
Markdown docs in `app/rag/docs/` are chunked by heading, embedded locally (fastembed, `all-MiniLM-L6-v2`, no API key; the model
downloads once into the `modelcache` volume) and stored in ChromaDB. The knowledge base starts empty and holds only what you upload (set `RAG_AUTOINGEST=true` / `RAG_BUILTIN_DOCS=true` to also index the built-in notes).
```bash
curl -X POST localhost:8000/knowledge/ingest                                  # re-sync built-in docs + uploads
curl -F file=@notes.pdf localhost:8000/knowledge/upload                       # .md or .pdf, kept in ./storage/knowledge
curl -X POST localhost:8000/knowledge/search -H 'content-type: application/json' -d '{"query":"trailing stop","k":3}'
curl localhost:8000/knowledge/documents
```
Re-ingesting only embeds changed chunks and removes chunks of deleted sources. To add built-in knowledge, drop a `.md` file in
`app/rag/docs/` and re-ingest. To change the embedding model, set `EMBEDDING_MODEL` (a new Chroma collection is used automatically,
then re-ingest).
`tests/test_rag_chroma_integration.py` runs against the compose ChromaDB (host port 8001) and skips if it is down.

## Multi-agent runs (Phase 5)
`POST /runs` starts a background pipeline: **research -> strategy -> verify -> backtest -> risk review** (Pydantic AI agents in
`app/agents/`, orchestrated by `app/agents/orchestrator.py`). Body: `dataset_id` plus an `idea` (plain English) and/or one of
`template_id` / `strategy_id` / `spec`, optional `start`, `end`, `capital`, `model`. It returns `202` with a run id.
- **Research** reads the knowledge base (RAG) and recent **market news** (`search_news`: public RSS feeds of Indian trading/investing
  sites such as Economic Times Markets, Mint, Business Standard, Moneycontrol, Investing.com; override with `NEWS_FEEDS`, disable with
  `NEWS_ENABLED=false`). Its output (concepts, considerations, `market_context`, `news_sources`) is passed to the strategy and verify agents.
  News describes today while the backtest runs on past data, so it guides strategy choice and risk caveats, never backtest evidence.
- **Strategy** returns the spec plus `explanation`, `assumptions`, `reasons` (why each choice, citing research) and `when_to_trade`.
- **Verify** checks the spec before it is backtested: fidelity to the idea, logic that can actually fire, risk settings, consistency with
  research. Code computes the facts (`app/engine/spec_check.py`: no stop loss, reward/risk, unused indicators, RSI range, ...); the agent
  returns a `verdict` (approved / needs_changes / rejected) with issues. It never blocks the run: the verdict is shown in the step output
  and as a warning, and the backtest still runs.
  **Loop:** if the agent-made spec is not approved, the issues go back to the strategy agent for a revision (at most 2 rounds), then it is
  verified again; the verify output has `revisions`, `history` and `final_spec` (the spec that is backtested). Specs you supply yourself
  (template / spec / saved strategy) are verified but never rewritten by the agents (only lots, stop/target and expiry are set
  from your limits).
- **Trade request flow (you execute the orders yourself; nothing is sent to a broker).** Describe the trade in free text and review how
  it was understood: `POST /runs/parse {"query": "BankNifty, capital 50k, max loss 2000, target 7777, EMA with RSI"}` returns
  `underlying, expiry, capital, max_loss, target_profit, preferred_indicators, idea, notes`. Then start the run with those fields:
  `POST /runs {"underlying": "BANKNIFTY", "expiry": "2025-10-28", "capital": 50000, "max_loss": 2000, "target_profit": 7777, "idea": "..."}`
  (no `dataset_id` needed: the newest dataset of that underlying with option candles is used).
  Name indicators in the idea (EMA, RSI, VWAP, Supertrend, ...) to get exactly those; leave them out and the agents choose from the
  research and market news. `max_loss` / `target_profit` are **per trade, in rupees**, for a bought option.
  Code (not the LLM) turns them into lots, stop-loss % and target % (`app/engine/sizing.py`) using the median ATM premium in the
  dataset, and the expiry date decides weekly vs monthly. The result is `steps[4].output.trade_plan` on `GET /runs/{id}`
  (risk step): side, strike rule, lots/quantity, stop/target, estimated max loss and profit, entry window, `when_to_trade`, `reasons`,
  verification verdict and backtest headline numbers. Premium estimates come from past data, so real fills differ.
- `GET /runs/{id}`: status, per-step output/usage/errors, and `backtest_run_id` (open it with the normal `/backtests/{id}` results API).
- `GET /runs/{id}/stream`: SSE (`step`, `run`, `done`). It polls the run record every 0.5 s, so late subscribers get the full history
  and it survives restarts. `GET /runs` lists runs. Runs cannot be cancelled yet.
- Strategy step is skipped (no LLM call) when no idea is given. A failed step marks the run `failed` and keeps earlier outputs
  (including the stored backtest). Runs left `running` after a restart are marked failed on startup.
- Model per agent: request `model` > `RESEARCH_MODEL`/`STRATEGY_MODEL`/`VERIFY_MODEL`/`BACKTEST_MODEL`/`RISK_MODEL` > `DEFAULT_MODEL`.
- **LLMs never compute numbers.** The backtest agent's `run_backtest` tool rejects any spec/dataset/range that differs from what
  the pipeline approved, metrics come from the engine, and the risk agent receives code-computed facts (`app/engine/summary.py`):
  exit-reason and CE/PE breakdown, profit concentration, losing streak, cost share, a +1 point slippage stress test, and flags
  (<30 trades, <5 days, drawdown >=20%, one trade/day >=40% of gross profit, profit that halves under stress, net loss).
- Try it: `PYTHONPATH=. uv run python scripts/smoke_run.py --idea "buy CE when 9 EMA crosses above 21 EMA"`.

**Offline demo model:** `ENABLE_MOCK_LLM=true` (and `DEFAULT_MODEL=mock:demo`) runs the whole pipeline with a scripted,
deterministic model that calls the same tools but does no real reasoning. Off by default; never used unless selected.

### Langfuse tracing (optional)
Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (and `LANGFUSE_HOST` for non-default regions). Pydantic AI is instrumented with
OpenTelemetry and exported to Langfuse; each run is one trace (session id, tag and metadata carry the `run_id`) with agent runs,
prompts, tool calls, tokens and latency. Without keys no tracing code runs. All log lines emitted during a run include `run_id`.
