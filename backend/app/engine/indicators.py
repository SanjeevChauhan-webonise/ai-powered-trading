"""Indicator registry. Add an indicator = one function + one @register decorator.

Each function takes the candle DataFrame (open/high/low/close/volume/timestamp) and a params dict
and returns a DataFrame whose columns are the declared outputs. Everything is causal: the value at
row t only depends on rows <= t.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

Params = dict[str, float]
IndicatorFn = Callable[[pd.DataFrame, Params], pd.DataFrame]


@dataclass(frozen=True)
class IndicatorDef:
    fn: IndicatorFn
    defaults: Params
    outputs: tuple[str, ...]

    @property
    def default_output(self) -> str:
        return self.outputs[0]


REGISTRY: dict[str, IndicatorDef] = {}


def register(name: str, defaults: Params, outputs: tuple[str, ...]) -> Callable[[IndicatorFn], IndicatorFn]:
    def deco(fn: IndicatorFn) -> IndicatorFn:
        REGISTRY[name] = IndicatorDef(fn, defaults, outputs)
        return fn

    return deco


def resolve_params(name: str, params: Params) -> Params:
    """Merge with defaults; reject unknown or non-positive params."""
    if name not in REGISTRY:
        raise ValueError(f"Unknown indicator '{name}'. Available: {sorted(REGISTRY)}")
    d = REGISTRY[name]
    unknown = set(params) - set(d.defaults)
    if unknown:
        raise ValueError(f"Indicator '{name}' has no params {sorted(unknown)}; allowed: {sorted(d.defaults)}")
    merged = {**d.defaults, **params}
    bad = [k for k, v in merged.items() if v <= 0]
    if bad:
        raise ValueError(f"Indicator '{name}' params must be > 0: {bad}")
    return merged


def compute(name: str, df: pd.DataFrame, params: Params | None = None) -> pd.DataFrame:
    d = REGISTRY[name]
    out = d.fn(df, resolve_params(name, params or {}))
    out.index = df.index
    return out[list(d.outputs)]


def _ema(x: pd.Series, period: int) -> pd.Series:
    """EMA with alpha=2/(period+1), seeded with the first value, defined from index period-1."""
    return x.ewm(span=period, adjust=False, min_periods=period).mean()


def _wilder(x: pd.Series, period: int) -> pd.Series:
    """Wilder smoothing seeded with the SMA of the first `period` valid values."""
    v = x.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) and valid[0] + period - 1 < len(v):
        seed = valid[0] + period - 1
        out[seed] = v[valid[0] : seed + 1].mean()
        for i in range(seed + 1, len(v)):
            out[i] = (out[i - 1] * (period - 1) + v[i]) / period
    return pd.Series(out, index=x.index)


def _true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    return _wilder(_true_range(df), period)


@register("sma", {"period": 20}, ("value",))
def sma(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    n = int(p["period"])
    return pd.DataFrame({"value": df["close"].rolling(n).mean()})


@register("ema", {"period": 20}, ("value",))
def ema(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    return pd.DataFrame({"value": _ema(df["close"], int(p["period"]))})


@register("rsi", {"period": 14}, ("value",))
def rsi(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    n = int(p["period"])
    delta = df["close"].diff()
    avg_gain = _wilder(delta.clip(lower=0), n)
    avg_loss = _wilder(-delta.clip(upper=0), n)
    rs = avg_gain / avg_loss.where(avg_loss != 0)
    value = 100 - 100 / (1 + rs)
    value = value.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0)).where(avg_gain.notna())
    return pd.DataFrame({"value": value})


@register("macd", {"fast": 12, "slow": 26, "signal": 9}, ("macd", "signal", "hist"))
def macd(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    line = _ema(df["close"], int(p["fast"])) - _ema(df["close"], int(p["slow"]))
    signal = _ema(line, int(p["signal"]))
    return pd.DataFrame({"macd": line, "signal": signal, "hist": line - signal})


@register("bollinger", {"period": 20, "std": 2}, ("mid", "upper", "lower"))
def bollinger(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    n = int(p["period"])
    mid = df["close"].rolling(n).mean()
    sd = df["close"].rolling(n).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + p["std"] * sd, "lower": mid - p["std"] * sd})


@register("atr", {"period": 14}, ("value",))
def atr(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    return pd.DataFrame({"value": _atr(df, int(p["period"]))})


@register("vwap", {}, ("value",))
def vwap(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Session VWAP, reset each day. Falls back to typical price while cumulative volume is 0."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df["timestamp"].dt.normalize()
    cum_pv = (tp * df["volume"]).groupby(day).cumsum()
    cum_v = df["volume"].groupby(day).cumsum()
    return pd.DataFrame({"value": (cum_pv / cum_v.where(cum_v > 0)).fillna(tp)})


@register("supertrend", {"period": 10, "multiplier": 3}, ("value", "direction"))
def supertrend(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """value = trailing line; direction = +1 (uptrend, line below price) or -1."""
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    a = _atr(df, int(p["period"])).to_numpy()
    close = df["close"].to_numpy()
    upper, lower = hl2 + p["multiplier"] * a, hl2 - p["multiplier"] * a
    n = len(close)
    f_up, f_lo = np.full(n, np.nan), np.full(n, np.nan)
    line, direction = np.full(n, np.nan), np.full(n, np.nan)
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid):
        s = valid[0]
        f_up[s], f_lo[s], direction[s], line[s] = upper[s], lower[s], 1, lower[s]
        for i in range(s + 1, n):
            f_up[i] = upper[i] if upper[i] < f_up[i - 1] or close[i - 1] > f_up[i - 1] else f_up[i - 1]
            f_lo[i] = lower[i] if lower[i] > f_lo[i - 1] or close[i - 1] < f_lo[i - 1] else f_lo[i - 1]
            if direction[i - 1] == 1:
                direction[i] = -1 if close[i] < f_lo[i] else 1
            else:
                direction[i] = 1 if close[i] > f_up[i] else -1
            line[i] = f_lo[i] if direction[i] == 1 else f_up[i]
    return pd.DataFrame({"value": line, "direction": direction})
