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
`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`). Model ids are `provider:model`, e.g.
`anthropic:claude-sonnet-5-5`. A request can pick any model; otherwise `<AGENT>_MODEL` (research / strategy / backtest / risk)
then `DEFAULT_MODEL` applies (`app/llm/registry.py: resolve_model`, `build_model`).

**Add a model:** append it to the provider's tuple in `app/llm/registry.py`, or set `EXTRA_MODELS=openai:some-new-model` in env.
Any model name works for requests even if unlisted; only the provider must be configured.
**Add a provider:** add a `Provider(...)` row, a Settings field for its key, and a `case` in `build_model`.

## Knowledge base / RAG (Phase 4)
Markdown docs in `app/rag/docs/` are chunked by heading, embedded locally (fastembed, `all-MiniLM-L6-v2`, no API key; the model
downloads once into the `modelcache` volume) and stored in ChromaDB. An empty knowledge base is filled in the background on startup.
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
`POST /runs` starts a background pipeline: **research -> strategy -> backtest -> risk review** (Pydantic AI agents in
`app/agents/`, orchestrated by `app/agents/orchestrator.py`). Body: `dataset_id` plus an `idea` (plain English) and/or one of
`template_id` / `strategy_id` / `spec`, optional `start`, `end`, `capital`, `model`. It returns `202` with a run id.
- `GET /runs/{id}`: status, per-step output/usage/errors, and `backtest_run_id` (open it with the normal `/backtests/{id}` results API).
- `GET /runs/{id}/stream`: SSE (`step`, `run`, `done`). It polls the run record every 0.5 s, so late subscribers get the full history
  and it survives restarts. `GET /runs` lists runs. Runs cannot be cancelled yet.
- Strategy step is skipped (no LLM call) when no idea is given. A failed step marks the run `failed` and keeps earlier outputs
  (including the stored backtest). Runs left `running` after a restart are marked failed on startup.
- Model per agent: request `model` > `RESEARCH_MODEL`/`STRATEGY_MODEL`/`BACKTEST_MODEL`/`RISK_MODEL` > `DEFAULT_MODEL`.
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
