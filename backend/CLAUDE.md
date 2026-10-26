# Backend

FastAPI + Postgres + ChromaDB. Check before done: `uv run pytest && uv run ruff check . && uv run mypy app`.

## Where things live
- `app/api/` routers: auth, datasets, strategies, backtests, runs (+SSE/poll), paper, knowledge, models, expiries, health.
- `app/agents/` Pydantic AI agents: `agents.py` (intake, ask, research, strategy, verify, backtest, risk), `prompts.py` (shared `<scope>` block
  in all prompts), `orchestrator.py` (pipeline), `trade_plan.py`, `mock.py` (offline `mock:demo` model).
- `app/engine/` pure, no LLM and no DB: `backtest.py`, `indicators.py` (registry), `conditions.py`, `metrics.py`, `sizing.py`, `lots.py`,
  `spec_check.py` and `verify.py` (facts for the verify agent), `summary.py`, `templates.py`.
- `app/guardrails/` `text.py` (input clean + injection block + PII redaction), `output.py` (no profit promises / buy-sell orders / quoted numbers),
  `limits.py` (per-user budgets).
- `app/paper/` market clock, prices, service. `app/rag/` chunker, embeddings (fastembed), Chroma store, retriever. `app/news/feeds.py` RSS.
- `app/llm/registry.py` provider:model ids. `app/core/` config, db models, security (scrypt), tracing (optional Langfuse), logging.
- `migrations/versions/` alembic 0001-0005. `otj/` one-off scripts. `scripts/` smoke runs. `upstox/` Upstox client + its own tests.

## Rules
- Agents never produce numbers. Lots, stop, target and expiry come from the user's rupee limits via `app/engine/sizing.py`.
- Engine functions stay pure and unit-testable. `signal_source: option` is not supported yet.
- New indicator: `@register(...)` in `app/engine/indicators.py` plus the name in `IndicatorType` (`app/schemas/strategy.py`); it must be causal,
  the parametrized no-lookahead test covers it.
- New model or provider: `app/llm/registry.py` (and a Settings field + `build_model` case for a provider).
- New table or column: alembic migration, and keep `user_id` scoping. Migrations run on container start.
- Changing `prompts.py` or `app/guardrails/*`: update `tests/test_prompts.py` / `tests/test_guardrails.py` and run `otj/eval_prompts.py`.
- Tracing is optional: the app must run with no Langfuse keys. Budgets in `.env`: `LLM_CALLS_PER_MINUTE`, `MAX_ACTIVE_RUNS_PER_USER`, `RUNS_PER_DAY`.
- `tests/test_rag_chroma_integration.py` needs the compose ChromaDB and skips if it is down.
- Env vars are documented in `.env.example`; keep it in sync with `app/core/config.py`.
