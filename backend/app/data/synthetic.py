"""Synthetic NIFTY-like data: random-walk underlying + Black-Scholes option chain.

Dataset fixture only; the backtest engine never prices options.
Run: python -m app.data.synthetic --out-dir storage/synthetic --format csv
"""

import argparse
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SESSION_MINUTES = 375  # 09:15 - 15:30
TICK = 0.05


@dataclass(frozen=True)
class SyntheticConfig:
    underlying: str = "NIFTY"
    start_date: date = date(2024, 1, 1)
    trading_days: int = 20
    start_price: float = 22000.0
    annual_vol: float = 0.15
    base_iv: float = 0.14
    strike_step: float = 50.0
    n_strikes: int = 10
    expiry_weekday: int = 3  # Thursday
    n_weekly_expiries: int = 3
    risk_free: float = 0.07
    seed: int = 42


def _trading_days(start: date, n: int) -> list[date]:
    days: list[date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _expiries(day: date, cfg: SyntheticConfig) -> list[date]:
    first = day + timedelta(days=(cfg.expiry_weekday - day.weekday()) % 7)
    exps = [first + timedelta(weeks=i) for i in range(cfg.n_weekly_expiries)]
    last_dom = calendar.monthrange(day.year, day.month)[1]
    monthly = date(day.year, day.month, last_dom)
    monthly -= timedelta(days=(monthly.weekday() - cfg.expiry_weekday) % 7)
    if monthly >= day and monthly not in exps:
        exps.append(monthly)
    return sorted(exps)


def _erf(x: np.ndarray) -> np.ndarray:  # Abramowitz-Stegun 7.1.26
    s = np.sign(x)
    x = np.abs(x)
    t = 1 / (1 + 0.3275911 * x)
    poly = ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
    return np.asarray(s * (1 - poly * np.exp(-x * x)))


def _ncdf(x: np.ndarray) -> np.ndarray:
    return np.asarray(0.5 * (1 + _erf(x / np.sqrt(2))))


def _black_scholes(s: np.ndarray, k: np.ndarray, t: np.ndarray, iv: np.ndarray, r: float, call: bool) -> np.ndarray:
    t = np.maximum(t, 1e-6)
    sq = iv * np.sqrt(t)
    d1 = (np.log(s / k) + (r + 0.5 * iv**2) * t) / sq
    d2 = d1 - sq
    disc = k * np.exp(-r * t)
    if call:
        return np.asarray(s * _ncdf(d1) - disc * _ncdf(d2))
    return np.asarray(disc * _ncdf(-d2) - s * _ncdf(-d1))


def _tick(x: np.ndarray) -> np.ndarray:
    return np.asarray(np.round(np.maximum(np.round(x / TICK) * TICK, TICK), 2))


def _underlying(cfg: SyntheticConfig, days: list[date], rng: np.random.Generator) -> pd.DataFrame:
    sigma = cfg.annual_vol / np.sqrt(252 * SESSION_MINUTES)
    u = np.linspace(-1, 1, SESSION_MINUTES)
    shape = 1 + 0.6 * u**2
    shape /= shape.mean()  # U-shaped intraday volatility
    frames = []
    prev = cfg.start_price
    for day in days:
        gap = rng.normal(0, cfg.annual_vol / np.sqrt(252) * 0.3)
        close = prev * np.exp(gap + np.cumsum(rng.normal(0, sigma, SESSION_MINUTES) * shape))
        open_ = np.concatenate([[prev * np.exp(gap)], close[:-1]])
        wick = np.abs(rng.normal(0, sigma * 0.5, (2, SESSION_MINUTES)))
        high = np.maximum(open_, close) * (1 + wick[0])
        low = np.minimum(open_, close) * (1 - wick[1])
        vol = (rng.lognormal(10, 0.5, SESSION_MINUTES) * (2 - shape.mean() + 0.5 * u**2)).astype("int64")
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": pd.date_range(f"{day} 09:15", periods=SESSION_MINUTES, freq="min"),
                    "symbol": cfg.underlying,
                    "open": np.round(open_, 2),
                    "high": np.round(high, 2),
                    "low": np.round(low, 2),
                    "close": np.round(close, 2),
                    "volume": vol,
                }
            )
        )
        prev = float(close[-1])
    return pd.concat(frames, ignore_index=True)


def _options_for_day(cfg: SyntheticConfig, day: date, u: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    center = round(float(u["open"].iloc[0]) / cfg.strike_step) * cfg.strike_step
    strikes = center + cfg.strike_step * np.arange(-cfg.n_strikes, cfg.n_strikes + 1)
    n_k = len(strikes)
    ts = u["timestamp"]
    spot = {c: u[c].to_numpy()[:, None] for c in ("open", "high", "low", "close")}
    k = strikes[None, :]
    frames = []
    for exp in _expiries(day, cfg):
        t_years = (
            (pd.Timestamp(exp) + pd.Timedelta(hours=15, minutes=30) - ts).dt.total_seconds().to_numpy() / (365 * 86400)
        )[:, None]
        iv = (
            cfg.base_iv
            * (1 + 1.5 * np.abs(np.log(k / spot["close"])))
            * (1 + rng.normal(0, 0.01, (SESSION_MINUTES, n_k)))
        )
        for typ in ("CE", "PE"):
            px = {c: _black_scholes(spot[c], k, t_years, iv, cfg.risk_free, typ == "CE") for c in spot}
            stack = np.stack(list(px.values()))
            o, c = _tick(px["open"]), _tick(px["close"])
            h, lo = _tick(stack.max(axis=0)), _tick(stack.min(axis=0))
            money = np.exp(-20 * np.abs(np.log(k / spot["close"])))
            volume = (rng.exponential(300, (SESSION_MINUTES, n_k)) * money).astype("int64")
            oi = (rng.integers(10_000, 500_000, n_k)[None, :] + rng.integers(0, 500, (SESSION_MINUTES, n_k))).astype(
                "int64"
            )
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp": np.repeat(ts.to_numpy(), n_k),
                        "underlying": cfg.underlying,
                        "expiry": pd.Timestamp(exp),
                        "strike": np.tile(strikes, SESSION_MINUTES),
                        "option_type": typ,
                        "open": o.ravel(),
                        "high": h.ravel(),
                        "low": lo.ravel(),
                        "close": c.ravel(),
                        "volume": volume.ravel(),
                        "oi": oi.ravel(),
                    }
                )  # fmt: skip
            )
    return pd.concat(frames, ignore_index=True)


def generate(cfg: SyntheticConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (underlying_candles, option_candles) in the standard schemas, 1-minute."""
    rng = np.random.default_rng(cfg.seed)
    days = _trading_days(cfg.start_date, cfg.trading_days)
    under = _underlying(cfg, days, rng)
    by_day = under.groupby(under["timestamp"].dt.date)
    opts = pd.concat([_options_for_day(cfg, d, by_day.get_group(d), rng) for d in days], ignore_index=True)
    return under, opts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=Path("storage/synthetic"))
    p.add_argument("--format", choices=["csv", "parquet"], default="csv")
    p.add_argument("--underlying", default="NIFTY")
    p.add_argument("--days", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--start-price", type=float, default=22000.0)
    p.add_argument("--strike-step", type=float, default=50.0)
    p.add_argument("--n-strikes", type=int, default=10)
    a = p.parse_args()
    cfg = SyntheticConfig(
        underlying=a.underlying, trading_days=a.days, seed=a.seed,
        start_price=a.start_price, strike_step=a.strike_step, n_strikes=a.n_strikes,
    )  # fmt: skip
    under, opts = generate(cfg)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in (("underlying", under), ("options", opts)):
        path = a.out_dir / f"{name}.{a.format}"
        df.to_csv(path, index=False) if a.format == "csv" else df.to_parquet(path, index=False)
        print(f"wrote {path} ({len(df)} rows)")


if __name__ == "__main__":
    main()
