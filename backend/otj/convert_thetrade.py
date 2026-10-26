"""Convert the thetrademarkk parquet download into the CSV layout the backtester loads (underlying.csv + options_<expiry>.csv).

Edit the SETTINGS block below, then run:

  PYTHONPATH=. uv run python otj/convert_thetrade.py

Reads option-data/thetrade/{index,options}/..., writes option-data/converted/<UNDERLYING>/1m/ in the standard columns
(naive IST). Per minute it keeps only strikes within N_STEPS strikes of the spot, and drops candles with no price, which
keeps a 1-minute backtest small enough to hold in memory. Only the last WEEKLY_DAYS (MONTHLY_DAYS for the month's last expiry) before each expiry are kept. Existing files are skipped, so a run can be resumed.
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------- SETTINGS
STEP = {"NIFTY": 50, "BANKNIFTY": 100}  # strike spacing near the money
START = date(2021, 7, 2)  # 5 years back from the last day in the dataset
END = date(2026, 7, 2)
WEEKLY_DAYS = 7  # days of candles kept before each weekly expiry (the engine trades the nearest expiry)
MONTHLY_DAYS = 35  # days kept before the last expiry of a month (monthly mode trades that one)
N_STEPS = 8  # strikes kept on each side of the spot
SRC = Path("option-data/thetrade")
OUT = Path("option-data/converted")
# -----------------------------------------------------------------------------


def _naive_ist(ts: pd.Series) -> pd.Series:
    return ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)


def convert(underlying: str) -> None:
    out = OUT / underlying / "1m"
    out.mkdir(parents=True, exist_ok=True)
    idx = pd.read_parquet(SRC / "index" / f"{underlying}.parquet")
    idx["timestamp"] = _naive_ist(idx["timestamp"])
    idx = idx[(idx["timestamp"].dt.date >= START) & (idx["timestamp"].dt.date <= END)]
    idx = idx[
        (idx["timestamp"].dt.time >= pd.Timestamp("09:15").time())
        & (idx["timestamp"].dt.time <= pd.Timestamp("15:29").time())
    ]
    idx = idx.drop_duplicates("timestamp").sort_values("timestamp")
    under = idx[["timestamp", "symbol", "open", "high", "low", "close", "volume"]]
    under.to_csv(out / "underlying.csv", index=False)
    logging.info("%s underlying: %d rows", underlying, len(under))
    spot = under.set_index("timestamp")["close"].rename("spot")

    files = sorted((SRC / "options" / underlying).glob("*.parquet"))
    expiries = [date.fromisoformat(f.stem) for f in files]
    month_end = {(e.year, e.month): e for e in expiries}  # last expiry listed in each month
    for f, expiry in zip(files, expiries, strict=True):
        path = out / f"options_{expiry.isoformat()}.csv"
        if expiry < START or path.exists():
            continue
        df = pd.read_parquet(f)
        df["timestamp"] = _naive_ist(df["timestamp"])
        df = df[(df["timestamp"].dt.date >= START) & (df["timestamp"].dt.date <= END)]
        days = MONTHLY_DAYS if month_end[(expiry.year, expiry.month)] == expiry else WEEKLY_DAYS
        df = df[df["timestamp"].dt.date >= expiry - timedelta(days=days)]
        df = df.join(spot, on="timestamp", how="inner")
        df = df[(df["close"] > 0) & ((df["strike"] - df["spot"]).abs() <= N_STEPS * STEP[underlying])]
        if df.empty:
            continue
        df = df.rename(columns={"open_interest": "oi", "symbol": "underlying"})
        df["expiry"] = expiry.isoformat()
        cols = [
            "timestamp",
            "underlying",
            "expiry",
            "strike",
            "option_type",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
        ]
        df[cols].sort_values(["timestamp", "strike", "option_type"]).to_csv(path, index=False)
        logging.info("wrote %s (%d rows)", path.name, len(df))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for u in STEP:
        convert(u)
    sys.exit(0)
