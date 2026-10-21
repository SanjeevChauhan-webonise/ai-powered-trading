import pandas as pd

from app.data.normalize import DataError
from app.data.validate import infer_timeframe_minutes
from app.schemas.data import DatasetKind


def resample(df: pd.DataFrame, kind: DatasetKind, minutes: int) -> pd.DataFrame:
    """Aggregate candles to a coarser timeframe. Bins are anchored at each day's first candle."""
    current = infer_timeframe_minutes(df["timestamp"])
    if current is None or minutes <= current or minutes % current != 0:
        raise DataError(f"Cannot resample {current}min data to {minutes}min (must be a larger multiple)")
    keys = ["symbol"] if kind == "underlying" else ["underlying", "expiry", "strike", "option_type"]
    out = df.sort_values("timestamp").copy()
    day = out["timestamp"].dt.normalize()
    session_start = out["timestamp"].groupby(day).transform("min")
    elapsed_min = (out["timestamp"] - session_start).dt.total_seconds() // 60
    out["timestamp"] = session_start + pd.to_timedelta((elapsed_min // minutes) * minutes, unit="min")
    agg: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "oi" in out.columns:
        agg["oi"] = "last"
    res = out.groupby([*keys, "timestamp"], sort=False).agg(agg).reset_index()
    cols = [c for c in df.columns if c in res.columns]
    return (
        res[cols]
        .sort_values(["timestamp", *keys[1:]] if kind == "options" else ["timestamp", *keys])
        .reset_index(drop=True)
    )
