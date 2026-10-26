"""Load CSVs (underlying.csv + options_<expiry>.csv, e.g. written by convert_thetrade.py) into the database, one dataset per underlying.

Edit the SETTINGS block below, then run:

  PYTHONPATH=. uv run python otj/load_csv_to_db.py

Reads underlying.csv and all options_*.csv from option-data/<UNDERLYING>/<N>m/, stores candles as parquet under
STORAGE_DIR and the dataset row in the database (DATABASE_URL / STORAGE_DIR from .env, as the API uses them).
Inside docker compose:  docker compose exec api python otj/load_csv_to_db.py
"""

import sys
from pathlib import Path

from app.core import models as core_models  # noqa: F401
from app.core.config import get_settings
from app.core.db import get_session
from app.data.csv_loader import load_export_dir
from app.data.normalize import DataError

# ----------------------------------------------------------------------------- SETTINGS
UNDERLYINGS = ["NIFTY"]  # any of: "NIFTY", "BANKNIFTY"
INTERVAL_MINUTES = 1  # must match the folder name the converter wrote (option-data/<UNDERLYING>/<N>m)
DATA_DIR = Path("option-data/converted")
# Multi-year 1-minute data does not fit in memory in the app; coarsen it while loading (underlying -> N minutes)
RESAMPLE_TO: dict[str, int] = {"NIFTY": 5}
# Lot sizes change over time; check the current NSE value before loading.
LOT_SIZES = {"NIFTY": 65, "BANKNIFTY": 30}
# Set an id to replace the data of an existing dataset instead of creating a new one, e.g. {"NIFTY": "ab12..."}
DATASET_IDS: dict[str, str] = {}
# -----------------------------------------------------------------------------


def main() -> int:
    settings = get_settings()
    session = get_session()
    failed = False
    try:
        for underlying in UNDERLYINGS:
            folder = DATA_DIR / underlying / f"{INTERVAL_MINUTES}m"
            try:
                row = load_export_dir(
                    session, settings, folder, underlying=underlying, lot_size=LOT_SIZES[underlying],
                    name=f"{underlying} {RESAMPLE_TO.get(underlying, INTERVAL_MINUTES)}m", dataset_id=DATASET_IDS.get(underlying), resample_to=RESAMPLE_TO.get(underlying),
                )  # fmt: skip
            except DataError as e:
                print(f"{underlying}: error: {e}")
                failed = True
                continue
            print(
                f"{underlying}: dataset {row.id}: {row.underlying_rows} underlying rows, "
                f"{row.options_rows} option rows, {len(row.expiries)} expiries, {row.start_date}..{row.end_date}"
            )
    finally:
        session.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
