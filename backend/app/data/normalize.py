from dataclasses import dataclass

import pandas as pd

from app.schemas.data import ColumnMapping, DatasetKind

UNDERLYING_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
OPTION_COLUMNS = [
    "timestamp", "underlying", "expiry", "strike", "option_type",
    "open", "high", "low", "close", "volume",
]  # fmt: skip
_OPTION_TYPES = {"CE": "CE", "C": "CE", "CALL": "CE", "PE": "PE", "P": "PE", "PUT": "PE"}
_PRICES = ["open", "high", "low", "close"]


class DataError(ValueError):
    """User-facing data problem (bad mapping, unreadable file, nothing valid)."""


@dataclass
class NormalizeStats:
    input_rows: int = 0
    bad_timestamps: int = 0
    bad_rows: int = 0
    invalid_ohlc: int = 0
    duplicates_removed: int = 0


def _get(raw: pd.DataFrame, source: str | None, field: str) -> pd.Series:
    if source is None:
        raise DataError(f"Mapping for '{field}' is required")
    if source not in raw.columns:
        raise DataError(f"Column '{source}' (mapped to '{field}') not found. Available: {list(raw.columns)}")
    return raw[source]


def _parse_timestamps(s: pd.Series, fmt: str | None, tz: str) -> pd.Series:
    try:
        ts = pd.to_datetime(s, format=fmt, errors="coerce")
    except (ValueError, TypeError):
        ts = pd.to_datetime(s, format=fmt, errors="coerce", utc=True)
    if ts.dtype == object:  # mixed UTC offsets
        ts = pd.to_datetime(s, format=fmt, errors="coerce", utc=True)
    if isinstance(ts.dtype, pd.DatetimeTZDtype):
        ts = ts.dt.tz_convert(tz).dt.tz_localize(None)
    return ts


def normalize(
    raw: pd.DataFrame, kind: DatasetKind, mapping: ColumnMapping, underlying: str
) -> tuple[pd.DataFrame, NormalizeStats]:
    """Apply the column mapping, clean, de-duplicate and sort. Timestamps are naive local time."""
    raw = raw.reset_index(drop=True)
    stats = NormalizeStats(input_rows=len(raw))

    ts_raw = _get(raw, mapping.timestamp, "timestamp")
    cols: dict[str, pd.Series] = {"timestamp": _parse_timestamps(ts_raw, mapping.timestamp_format, mapping.timezone)}
    if kind == "underlying":
        cols["symbol"] = (
            _get(raw, mapping.symbol, "symbol").astype(str).str.strip()
            if mapping.symbol
            else pd.Series(underlying, index=raw.index)
        )
    else:
        cols["underlying"] = (
            _get(raw, mapping.underlying, "underlying").astype(str).str.strip()
            if mapping.underlying
            else pd.Series(underlying, index=raw.index)
        )
        cols["expiry"] = pd.to_datetime(_get(raw, mapping.expiry, "expiry"), errors="coerce").dt.normalize()
        cols["strike"] = pd.to_numeric(_get(raw, mapping.strike, "strike"), errors="coerce")
        cols["option_type"] = (
            _get(raw, mapping.option_type, "option_type").astype(str).str.strip().str.upper().map(_OPTION_TYPES)
        )
    for f in _PRICES:
        cols[f] = pd.to_numeric(_get(raw, getattr(mapping, f), f), errors="coerce")
    cols["volume"] = (
        pd.to_numeric(_get(raw, mapping.volume, "volume"), errors="coerce").fillna(0).astype("int64")
        if mapping.volume
        else pd.Series(0, index=raw.index, dtype="int64")
    )
    if mapping.oi:
        cols["oi"] = pd.to_numeric(_get(raw, mapping.oi, "oi"), errors="coerce")
    df = pd.DataFrame(cols)

    bad_ts = df["timestamp"].isna()
    stats.bad_timestamps = int(bad_ts.sum())
    required = [c for c in df.columns if c not in ("timestamp", "volume", "oi")]
    bad_other = ~bad_ts & df[required].isna().any(axis=1)
    stats.bad_rows = int(bad_other.sum())
    df = df[~(bad_ts | bad_other)]

    px = df[_PRICES]
    floor_bad = (px < 0).any(axis=1) if kind == "options" else (px <= 0).any(axis=1)
    invalid = (
        floor_bad
        | (df["high"] < df["low"])
        | (df["open"] > df["high"]) | (df["open"] < df["low"])
        | (df["close"] > df["high"]) | (df["close"] < df["low"])
    )  # fmt: skip
    stats.invalid_ohlc = int(invalid.sum())
    df = df[~invalid]

    key = ["timestamp", "symbol"] if kind == "underlying" else ["timestamp", "expiry", "strike", "option_type"]
    dup = df.duplicated(key, keep="last")
    stats.duplicates_removed = int(dup.sum())
    df = df[~dup].sort_values(key).reset_index(drop=True)
    if df.empty:
        raise DataError("No valid rows remain after normalization")
    return df, stats
