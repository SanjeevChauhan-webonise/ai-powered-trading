# Test report: backtesting branch

Date: 2026-10-26 · Branch: `feature/backtesting`

A full pass over every flow of the app after two changes on this branch: paper trading was removed (commit `408ece1`) and Upstox was
removed (data import and export, the `upstox/` package and the live `/expiries` endpoint). It also covers a test on real historical
NIFTY and BANKNIFTY data, which found and fixed a data bug (see "Bug found and fixed").
Educational prototype only: no live trading, simulated money only.

## Summary

| Area | Result |
|---|---|
| Backend unit and integration tests (`uv run pytest`) | 261 passed, 1 skipped (the Chroma integration test skips when its container is down) |
| Backend lint (`ruff check`) | clean |
| Backend types (`mypy app`) | 4 errors, all in `app/engine/verify.py` (see Known issues) |
| Frontend lint (`eslint`) and types (`tsc`) | 0 errors; 2 warnings in `lib/api.ts` (existing) |
| Frontend build (`npm run build`) | passed; no `/paper-trading` route |
| API flow checks against the running stack | 58/58 passed |
| Browser (UI) flow checks, headless Chrome | 16/16 passed |
| Historical data: 4 full 5-year backtests, 6 yearly slices, raw-file cross-check, AI run | all passed after the fix (see below) |
| Database migrations on a fresh database | `0001` to `0006` applied; no `paper_*` tables; removed routes return 404 |

## How it was tested

- **Isolated stack.** A separate Docker Compose project (`tradingtest`) with its own Postgres, ChromaDB and storage folder, on ports 8100 (API),
  5532, 8101 and 3100 (frontend dev server). The normal local data (`backend_pgdata` and `./storage`) was not touched.
- **Mock LLM.** The final runs set `DEFAULT_MODEL`, `RESEARCH_MODEL`, `STRATEGY_MODEL`, `VERIFY_MODEL`, `BACKTEST_MODEL` and `RISK_MODEL` to
  `mock:demo`, and the API log showed 0 calls to any real provider. The pipeline then runs deterministically with no key and no cost. This
  tests the plumbing (agents, tools, code guardrails, persistence, SSE, UI) but **not the quality of real model answers**.
  The numbers do not depend on the model: the same historical AI run gave identical trades and P&L with a real `gpt-4o-mini` backtest step and with the mock.
- **API flows.** A Python script drove the REST API with two fresh accounts (beginner and expert), a synthetic NIFTY dataset and an uploaded CSV dataset.
- **UI flows.** A Playwright script drove headless Google Chrome against `next dev` (`NEXT_PUBLIC_API_URL=http://localhost:8100`).
- **Historical data.** The converted TheTrade files in `backend/option-data/converted` were loaded with `otj/load_csv_to_db.py` (coarsened to 5-minute
  candles, 46 s, about 2 GB of memory) and backtested through the API.

## Bug found and fixed: wrong open and close in coarsened option candles

`_coarsen_options` in `app/data/csv_loader.py` floored each timestamp to its 5-minute bin and only then sorted by timestamp. Inside a bin every row
then had the same timestamp, so the (non-stable) sort left them in arbitrary order and the `first` (open) and `last` (close) aggregates picked the wrong
minute. High, low and volume were correct. Example: for one NIFTY put the 10:55 candle had open 73.85 (the open of the 10:58 minute) instead of 73.30.

- **Impact:** any dataset loaded with `RESAMPLE_TO` (or `resample_to`) had wrong option opens and closes, so entry fills, stops and P&L were off.
  The engine's own verification did not catch it because it re-checks trades against the stored candles. **Datasets loaded before this fix must be reloaded.**
- **Fix:** sort by the original minute (stable) before flooring. Test `test_coarsen_options_open_and_close_follow_time_not_row_order` fails on the old code and passes now.
- **How it was found:** the raw-file cross-check below matched 0 of 80 sampled trades before the fix and 80 of 80 after it.

## Historical data results

Real NIFTY and BANKNIFTY option data, loaded as 5-minute candles.

| Underlying | Range | Timeframe | Underlying rows | Option rows | Expiries |
|---|---|---|---|---|---|
| NIFTY | 2021-07-02 to 2026-07-02 | 5 min | 91,923 | 3,891,100 | 259 |
| BANKNIFTY | 2021-07-02 to 2026-07-02 | 5 min | 92,368 | 1,269,704 | 60 |

### Full-history backtests (capital Rs 5,00,000, built-in templates, default settings)

| Underlying | Template | Trades | Net P&L (Rs) | Net P&L before the fix (Rs) | Win rate | Profit factor | Max drawdown | Verified trades | Time |
|---|---|---|---|---|---|---|---|---|---|
| NIFTY | ema_crossover | 3,330 | -27,500 | -119,897 | 31.41% | 0.9871 | 22.6817% | 3330/3330 | 64.2 s |
| NIFTY | rsi_reversal | 2,161 | -276,621 | -277,205 | 32.9% | 0.8415 | 59.9744% | 2161/2161 | 45.6 s |
| BANKNIFTY | ema_crossover | 1,508 | -110,447 | -89,063 | 29.11% | 0.91 | 34.732% | 1508/1508 | 13.2 s |
| BANKNIFTY | rsi_reversal | 836 | -134,061 | -98,267 | 36.24% | 0.8613 | 33.8656% | 836/836 | 8.7 s |

"Verified trades" is the engine's independent recomputation of every trade (quantity, entry and exit candle, costs, P&L) and whether the totals match.
The templates are demos, not tuned strategies: all four lose money over five years after costs, which is expected and not a finding about the engine.

### NIFTY EMA crossover by calendar year (date-range filter)

| Year | Trades | Net P&L (Rs) | Win rate | Profit factor | Max drawdown | Verified trades | All entries inside the range |
|---|---|---|---|---|---|---|---|
| 2021 | 344 | -12,336 | 30.23% | 0.931 | 8.3294% | 344/344 | yes |
| 2022 | 675 | 8,931 | 32.74% | 1.0209 | 9.4131% | 675/675 | yes |
| 2023 | 658 | -36,828 | 30.24% | 0.8835 | 9.5238% | 658/658 | yes |
| 2024 | 703 | -5,516 | 30.01% | 0.9886 | 15.5075% | 703/703 | yes |
| 2025 | 684 | -37,538 | 31.87% | 0.9256 | 9.9362% | 684/684 | yes |
| 2026 | 266 | 55,788 | 34.96% | 1.2608 | 2.9509% | 266/266 | yes |

### Invariants on every trade

| Run | Trades | Violations | Lot sizes used | Exit reasons |
|---|---|---|---|---|
| NIFTY ema_crossover | 3330 | 0 | 65, 75 | end_of_data 2, signal 1037, square_off 321, stop_loss 1208, target 762 |
| NIFTY rsi_reversal | 2161 | 0 | 65, 75 | end_of_data 1, signal 27, square_off 287, stop_loss 1324, target 522 |
| BANKNIFTY ema_crossover | 1508 | 0 | 30, 35 | end_of_data 1, signal 706, square_off 230, stop_loss 349, target 222 |
| BANKNIFTY rsi_reversal | 836 | 0 | 30, 35 | end_of_data 4, signal 37, square_off 232, stop_loss 412, target 151 |

Checked on every trade: exit not before entry, entry and exit on the same day, within market hours, quantity = lots x lot size, net P&L = gross - brokerage - taxes,
no overlapping positions, and the daily trade cap. All counts were zero.

### Cross-check against the raw 1-minute files

For 40 random EMA-crossover trades per underlying, the engine's entry price was compared with the open of the first 1-minute candle of that contract in the raw CSV for the entry bin.

| Underlying | Sampled | Match | Mismatch | No raw row |
|---|---|---|---|---|
| NIFTY | 40 | 40 | 0 | 0 |
| BANKNIFTY | 40 | 40 | 0 | 0 |

### AI pipeline on historical data (mock model)

NIFTY, capital 5,00,000, max loss 5,000, target 10,000, idea "EMA crossover with RSI filter", range 2025: status **completed** in 22.2 s, all five steps completed,
401 trades, net P&L -89,948, 401/401 trades verified, lots 3 (computed in code from the max-loss limit).

## API flows (58/58)

| Flow | Passed |
|---|---|
| auth | 14/14 |
| datasets | 7/7 |
| strategies | 6/6 |
| backtests | 8/8 |
| models | 1/1 |
| knowledge | 6/6 |
| removed | 1/1 |
| runs | 9/9 |
| guardrails | 6/6 |

| Flow | Check | Result | Notes |
|---|---|---|---|
| auth | health reports postgres and chromadb up | PASS | {'postgres': 'up', 'chromadb': 'up'} |
| auth | protected endpoint without token is 401 | PASS |  |
| auth | removed /paper routes are gone (404) | PASS |  |
| auth | register beginner | PASS | <email> |
| auth | register expert | PASS |  |
| auth | duplicate email is rejected | PASS |  |
| auth | short password is rejected | PASS |  |
| auth | login with right password | PASS |  |
| auth | login with wrong password is 401, no email hint | PASS |  |
| auth | GET /auth/me | PASS | <email> |
| auth | PATCH /auth/me changes name and level | PASS |  |
| auth | PATCH level back to beginner | PASS |  |
| auth | change password ends other logins | PASS |  |
| auth | logout invalidates token | PASS |  |
| datasets | create synthetic dataset | PASS | keys=['created_at', 'end_date', 'expiries', 'id', 'lot_size', 'name', 'options_rows', 'quality'] |
| datasets | list datasets contains it | PASS |  |
| datasets | dataset detail has metadata | PASS | {"id": "<id>", "name": "Synthetic NIFTY", "underlying": "NIFTY", "lot_size": 75, "timeframe_minutes": 1, "star |
| datasets | dataset is shared with other users | PASS |  |
| datasets | unknown dataset is 404 | PASS |  |
| datasets | upload CSV with column mapping | PASS |  |
| datasets | upload with wrong mapping is rejected | PASS |  |
| strategies | list templates | PASS | ema_crossover, rsi_reversal |
| strategies | validate a template spec | PASS | {"valid": true, "errors": [], "spec": {"name": "EMA Crossover", "description": "Buy CE when the fast EMA cross |
| strategies | validate rejects an unknown indicator | PASS |  |
| strategies | save strategy | PASS |  |
| strategies | list and get strategy | PASS |  |
| strategies | strategy is private to its owner (404) | PASS |  |
| backtests | direct backtest from template | PASS | trades=None net=None |
| backtests | every template backtests without error | PASS | ema_crossover, rsi_reversal |
| backtests | get backtest result (trades, curve) | PASS | keys=['id', 'dataset_id', 'strategy_id', 'strategy_name', 'start', 'end', 'capital', 'status', 'total_pnl', 'n |
| backtests | list backtests | PASS |  |
| backtests | backtest is private (404 for another user) | PASS |  |
| backtests | backtest from a saved strategy | PASS |  |
| backtests | dataset without option candles gives a clear result | PASS | HTTP 400: {"detail":"Dataset needs both underlying and option candles"} |
| backtests | backtest with explicit date range | PASS |  |
| models | GET /models lists the mock model as default | PASS | default=mock:demo available=True n=5 |
| knowledge | upload a markdown document | PASS | {"source":"uploads/theta_c3a5f1.md","chunks":2} |
| knowledge | re-ingest knowledge base | PASS | {"documents":3,"chunks_total":5,"chunks_added":0,"chunks_removed":0,"sources_removed":[]} |
| knowledge | documents list includes upload | PASS |  |
| knowledge | semantic search finds the uploaded note | PASS | 3 results, top source=uploads/theta_45f1d3.md |
| knowledge | browse chunks of a document | PASS | 2 chunks |
| knowledge | document with injection text is handled | PASS | HTTP 200 |
| removed | Upstox and /expiries routes are gone (404) | PASS |  |
| runs | parse a free-text trade request | PASS | {"intent": "strategy", "underlying": "BANKNIFTY", "capital": 50000.0, "max_loss": 2000.0, "target_profit": 777 |
| guardrails | off-topic request is flagged off_topic | PASS | intent=off_topic |
| guardrails | prompt injection is blocked before the model | PASS | HTTP 200: {"intent":"off_topic","refusal":"This tool only handles NIFTY and BANKNIFTY options trading: strateg |
| runs | ask: in-scope options question is answered | PASS | answer: (mock) Theta is the daily loss of option value from time passing. |
| guardrails | ask: out-of-scope question is refused | PASS | This tool only handles NIFTY and BANKNIFTY options trading. Ask me about a strategy, a backtest or an option c |
| guardrails | PII (PAN, email) is redacted | PASS | PAN not echoed |
| runs | pipeline from a template completes (verify + backtest + risk) | PASS | steps={'research': 'completed', 'strategy': 'skipped', 'verify': 'completed', 'backtest': 'completed', 'risk': |
| runs | pipeline from a plain-English idea completes | PASS | steps={'research': 'completed', 'strategy': 'completed', 'verify': 'completed', 'backtest': 'completed', 'risk |
| runs | run record has all five steps with outputs | PASS | steps=['research', 'strategy', 'verify', 'backtest', 'risk']; verify verdict=approved |
| runs | list runs shows own runs | PASS |  |
| runs | run is private (404 for another user) | PASS |  |
| runs | SSE stream delivers progress events | PASS | events=['done', 'run', 'step'] |
| runs | trade-request flow (underlying, capital, max loss, target) without dataset_id | PASS | completed; plan keys=['underlying', 'expiry_date', 'expiry_type', 'strategy', 'bullish_signal_action', 'bearis |
| guardrails | beginner max-loss above the cap is capped or rejected | PASS | beginner with max loss 90% of capital: HTTP 400 {"detail":"Max loss per trade is 90.0% of your capital, above  |
| guardrails | per-minute LLM budget returns 429 | PASS | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429] |

## UI flows (16/16)

| Flow | Check | Result | Notes |
|---|---|---|---|
| auth | unauthenticated visit redirects to /login | PASS |  |
| auth | wrong password shows an error | PASS |  |
| auth | create an account (beginner) via the UI | PASS |  |
| nav | sidebar has no Paper Trading link or paper balance | PASS | nav: Dashboard / Strategy Desk / Backtest / Profit & Loss / Knowledge Base / Settings & Models |
| nav | /paper-trading is a 404 page | PASS |  |
| dashboard | dashboard renders counts and lists | PASS |  |
| backtest | backtest list page loads | PASS |  |
| backtest | new backtest: choose dataset + template and run | PASS | /results/<id> |
| backtest | results page shows metrics, charts and trade log | PASS | charts=5 trade-rows=34 |
| pnl | P&L page shows only the Backtests view (no tabs) | PASS |  |
| knowledge | knowledge base page loads and uploads a note | PASS |  |
| settings | settings page shows profile, level and models | PASS |  |
| desk | Strategy Desk: ask a general question (answered directly) | PASS |  |
| desk | Strategy Desk: off-topic request is refused | PASS |  |
| desk | Strategy Desk: trade request runs the 5-step pipeline to a plan | PASS | plan produced and backtest link enabled |
| auth | log out returns to /login | PASS |  |

## What the checks show

- **Removed features are gone.** No `/paper` routes or tables, no Upstox import, export or `/expiries` routes, no paper UI, and `/paper-trading` returns a 404 page.
  The Strategy Desk expiry dropdown still works from the usual weekday rule and says to confirm the date with your broker.
- **Core pipeline works end to end.** Template and plain-English runs complete research, strategy, verify, backtest and risk review.
- **Guardrails hold in code.** Off-topic requests are refused, prompt-injection text is stopped before the model, PAN and email are not echoed, a beginner's
  max loss above the 5% cap gets HTTP 400, and the per-minute LLM budget returns HTTP 429.
- **Data is private per user.** Another user gets 404 for strategies, backtests and runs; datasets stay shared.
- **Sessions behave.** Changing the password ends other logins and logout invalidates the token.
- **The backtest engine agrees with the raw data** (after the fix) and passes its own per-trade verification on about 7,800 historical trades.

## Not tested

- **Real LLM providers.** No real model answers were evaluated. Run `otj/eval_prompts.py` with a real model after any prompt or guard change.
- **Live news.** The research step ran with the mock model; fetching the RSS feeds is covered only by `tests/test_news.py`.
- **Loading through the UI.** There is no dataset upload page; upload and loading were tested through the API and the `otj` scripts only.
- **The TheTrade conversion step** (`otj/convert_thetrade.py`) was not re-run; the already converted files were used.
- **Mobile layouts and browsers other than Chrome.**

## Known issues and observations

1. **mypy fails on `app/engine/verify.py`** (lines 58, 64, 67, 70): a `str` or a plain string literal is assigned to a variable typed as the exit-reason `Literal`. Not changed by this work.
2. **Old lot sizes.** `app/engine/lots.py` starts at 2024-11-20, so contracts expiring before that use the dataset's default lot size (NIFTY 65, BANKNIFTY 30),
   not the size in force at the time. Quantities, and so rupee P&L, for 2021 to 2024 trades are scaled by today's lot size. Win rate and profit factor are not affected.
3. **Duplicate rows in the converted CSVs.** Every 1-minute candle appears twice in `option-data/converted/*/1m/options_*.csv`. The loader removes duplicates, so the data is correct,
   but the files are about twice as large as needed; the cause is in the conversion step and was not investigated.
4. **Automatic dataset choice.** A trade request without `dataset_id` uses the newest dataset of that underlying with option candles, even a synthetic one, and `/backtest/new`
   preselects the newest dataset even when it has no option candles (the run then fails with a clear message). Pass `dataset_id` when several datasets exist.
5. **Dev-server console error.** In `next dev`, every route logs "Could not validate that a segment in your UI has instant navigation" and shows a "1 Insight" badge.
   It did not affect any flow and the production build passes; it was not checked against earlier commits.
6. **Migration `0006` downgrade** does not recreate the paper tables (see `0005` to rebuild them).
7. The `.docx` and `.pdf` guides in `docs/` may still describe paper trading and Upstox.
8. **Test setup lesson.** `backend/.env` can set per-agent models (for example `BACKTEST_MODEL=openai:gpt-4o-mini`), which override `DEFAULT_MODEL`.
   An earlier round of this test only set `DEFAULT_MODEL=mock:demo`, so the backtest step of each pipeline run made one small real OpenAI call. Those results were
   re-run with every agent model set to `mock:demo`, and the numbers above come from the clean runs.

## How to repeat

```bash
cd backend && uv run pytest && uv run ruff check . && uv run mypy app
cd frontend && npm run lint && npm run build
# Offline run: in backend/.env set ENABLE_MOCK_LLM=true and DEFAULT_MODEL, RESEARCH_MODEL, STRATEGY_MODEL, VERIFY_MODEL, BACKTEST_MODEL, RISK_MODEL to mock:demo, then
cd backend && docker compose up --build
cd frontend && npm run dev
# Historical data: convert, then load (settings are edited inside each script)
cd backend && PYTHONPATH=. uv run python otj/convert_thetrade.py && PYTHONPATH=. uv run python otj/load_csv_to_db.py
```
