"""Download NIFTY / BANKNIFTY history from Upstox into CSV files, one options file per expiry.

Edit the SETTINGS block below, then run:

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

from dotenv import load_dotenv

from upstox import UpstoxClient, UpstoxError, fetch_daily, fetch_underlying
from upstox.export import export_range

# ----------------------------------------------------------------------------- SETTINGS
UNDERLYINGS = [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
]  # "NIFTY" (Nifty 50), "BANKNIFTY" (Nifty Bank), "FINNIFTY" (Fin Service)
START = date(2022, 1, 1)  # Upstox minute candles start Jan 2022; option candles only exist for the last ~6 months
END = date.today()
INTERVAL_MINUTES = 1  # 1, 3, 5, 15 or 30
INCLUDE_OPTIONS = False  # False = underlying candles only (no Upstox Plus needed)
OPTION_TYPES = ("CE", "PE")  # ("CE",) = calls only, ("PE",) = puts only
EXPIRY_TYPE = "all"  # "all", "weekly" or "monthly"
LAST_EXPIRIES = None  # e.g. 8 = only the most recent 8 expiries inside START..END; None = all
N_STRIKES = 10  # strikes on each side of ATM
DAILY_START = date(2000, 1, 1)  # daily candles go back to Jan 2000 (includes INDIAVIX)
DAILY_UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "INDIAVIX"]
VIX_MINUTE = True  # also INDIAVIX minute candles (from Jan 2022)
OUT_DIR = Path("option-data")
# -----------------------------------------------------------------------------


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / "upstox" / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    client = UpstoxClient(os.environ.get("UPSTOX_ACCESS_TOKEN", ""))
    for underlying in UNDERLYINGS:
        logging.info("=== %s %s..%s %dm ===", underlying, START, END, INTERVAL_MINUTES)
        export_range(
            client, underlying, INTERVAL_MINUTES, START, END, OUT_DIR / underlying / f"{INTERVAL_MINUTES}m",
            n_strikes=N_STRIKES, include_options=INCLUDE_OPTIONS, option_types=OPTION_TYPES,
            expiry_type=EXPIRY_TYPE, last_expiries=LAST_EXPIRIES,
        )  # fmt: skip
    for u in DAILY_UNDERLYINGS:  # option-data/<UNDERLYING>/daily/underlying.csv
        path = OUT_DIR / u / "daily" / "underlying.csv"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            df = fetch_daily(client, u, DAILY_START, END)
            df.to_csv(path, index=False)
            logging.info("wrote %s (%d rows)", path, len(df))
    path = OUT_DIR / "INDIAVIX" / f"{INTERVAL_MINUTES}m" / "underlying.csv"
    if VIX_MINUTE and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        df = fetch_underlying(client, "INDIAVIX", INTERVAL_MINUTES, START, END)
        df = df.drop_duplicates("timestamp").sort_values("timestamp")
        df.to_csv(path, index=False)
        logging.info("wrote %s (%d rows)", path, len(df))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UpstoxError as e:
        sys.exit(f"error: {e}")
