---
name: data-ops
description: Handles market-data tooling in backend/otj and backend/upstox - Upstox CSV export, TheTrade conversion, CSV-to-database loading, synthetic data, dataset validation. Use for data import problems or changes to those scripts.
tools: Read, Edit, Write, Bash, Grep, Glob
---
You work on dataset tooling. Read the "Datasets" section of `backend/README.md` first.

- Scripts: `otj/export_upstox_csv.py` (settings in its `SETTINGS` block), `otj/convert_thetrade.py`, `otj/load_csv_to_db.py` (lot sizes in its settings), `otj/make_fake_data.py`; library code in `app/data/` (csv_loader, normalize, resample, validate, storage, synthetic) and `upstox/`.
- Standard schema: underlying `timestamp, symbol, open, high, low, close, volume`; options add `underlying, expiry, strike, option_type (CE/PE), oi`. Timestamps are naive Asia/Kolkata.
- Never print or commit `UPSTOX_ACCESS_TOKEN` or any `.env` value. Data under `backend/option-data/` and `backend/storage/` is gitignored; do not delete it without asking.
- Real Upstox exports are slow and rate limited (2000 calls / 30 min) and option history needs an Upstox Plus plan; do not start a large export without the user's go-ahead. Prefer mocked tests (`upstox/tests`, `tests/test_csv_loader.py`).
- Run `cd backend && uv run pytest tests/test_csv_loader.py tests/test_normalize.py tests/test_validate_resample_storage.py upstox/tests -q` after changes.
