"""Make FAKE NIFTY / BANKNIFTY candles as CSV for testing (random-walk underlying + Black-Scholes options).

Edit the SETTINGS block below, then run:

  PYTHONPATH=. uv run python otj/make_fake_data.py

Writes option-data/fake/<UNDERLYING>/<N>m/underlying.csv and options_<expiry>.csv, the same layout and columns as
otj/convert_thetrade.py, so otj/load_csv_to_db.py can load them (set its DATA_DIR to option-data/fake and its
INTERVAL_MINUTES to match). The prices are made up and have NO real edge; use them only to test the app.
"""

from datetime import date
from pathlib import Path

from app.data.resample import resample
from app.data.synthetic import SyntheticConfig, generate

# ----------------------------------------------------------------------------- SETTINGS
START = date(2026, 9, 1)
TRADING_DAYS = 22  # about one month
INTERVAL_MINUTES = 5  # candles are generated per minute, then resampled to this
N_STRIKES = 10  # strikes on each side of ATM
OUT_DIR = Path("option-data/fake")
UNDERLYINGS = {
    "NIFTY": SyntheticConfig(
        underlying="NIFTY", start_price=25_900.0, strike_step=50.0, annual_vol=0.14, base_iv=0.13,
        expiry_weekday=1, n_weekly_expiries=3, seed=11,
    ),
    "BANKNIFTY": SyntheticConfig(
        underlying="BANKNIFTY", start_price=57_000.0, strike_step=100.0, annual_vol=0.18, base_iv=0.16,
        expiry_weekday=1, n_weekly_expiries=1, seed=22,
    ),
}  # fmt: skip
# -----------------------------------------------------------------------------


def main() -> None:
    for name, base in UNDERLYINGS.items():
        cfg = SyntheticConfig(
            **{**base.__dict__, "start_date": START, "trading_days": TRADING_DAYS, "n_strikes": N_STRIKES}
        )
        under, opts = generate(cfg)
        under = resample(under, "underlying", INTERVAL_MINUTES) if INTERVAL_MINUTES > 1 else under
        opts = resample(opts, "options", INTERVAL_MINUTES) if INTERVAL_MINUTES > 1 else opts
        out = OUT_DIR / name / f"{INTERVAL_MINUTES}m"
        out.mkdir(parents=True, exist_ok=True)
        under.to_csv(out / "underlying.csv", index=False)
        print(f"{name}: wrote {out / 'underlying.csv'} ({len(under)} rows)")
        for expiry, g in opts.groupby("expiry"):
            g = g.assign(expiry=g["expiry"].dt.date)
            path = out / f"options_{expiry.date().isoformat()}.csv"
            g.to_csv(path, index=False)
            print(f"{name}: wrote {path.name} ({len(g)} rows)")


if __name__ == "__main__":
    main()
