"""Download NIFTY / BANKNIFTY history from Upstox into CSV files, one options file per expiry.

Edit the SETTINGS block below, then run:

  export UPSTOX_ACCESS_TOKEN=...
  PYTHONPATH=. uv run python otj/export_upstox_csv.py

Writes option-data/<UNDERLYING>/<N>m/underlying.csv and options_<expiry>.csv (standard upload columns, naive IST).
Re-running skips files that already exist, so an interrupted export can be resumed.
Load later with otj/load_csv_to_db.py. Option candles need an Upstox Plus plan and only exist for expiries
from the last ~6 months.
"""

import logging
import os
import sys
from datetime import date
from pathlib import Path

from app.data.export import export_range
from app.data.upstox import UpstoxClient, UpstoxError

# ----------------------------------------------------------------------------- SETTINGS
UNDERLYINGS = ["NIFTY", "BANKNIFTY"]  # any of: "NIFTY" (Nifty 50), "BANKNIFTY" (Nifty Bank)
START = date(2025, 6, 1)
END = date(2025, 9, 30)
INTERVAL_MINUTES = 1  # 1, 3, 5, 15 or 30
INCLUDE_OPTIONS = True  # False = underlying candles only (no Upstox Plus needed)
OPTION_TYPES = ("CE", "PE")  # ("CE",) = calls only, ("PE",) = puts only
EXPIRY_TYPE = "all"  # "all", "weekly" or "monthly"
LAST_EXPIRIES = None  # e.g. 8 = only the most recent 8 expiries inside START..END; None = all
N_STRIKES = 10  # strikes on each side of ATM
OUT_DIR = Path("option-data")
# -----------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    client = UpstoxClient(os.environ.get("UPSTOX_ACCESS_TOKEN", ""))
    for underlying in UNDERLYINGS:
        logging.info("=== %s %s..%s %dm ===", underlying, START, END, INTERVAL_MINUTES)
        export_range(
            client, underlying, INTERVAL_MINUTES, START, END, OUT_DIR / underlying / f"{INTERVAL_MINUTES}m",
            n_strikes=N_STRIKES, include_options=INCLUDE_OPTIONS, option_types=OPTION_TYPES,
            expiry_type=EXPIRY_TYPE, last_expiries=LAST_EXPIRIES,
        )  # fmt: skip
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UpstoxError as e:
        sys.exit(f"error: {e}")
