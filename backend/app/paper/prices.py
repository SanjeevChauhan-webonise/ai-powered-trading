"""Simulated market prices for paper trading: everything is read from a dataset's Parquet files.

The "market" is the dataset replayed by a clock, so a price is the close of the contract's candle at (or just before)
the clock time. Reads are filtered to one contract or one candle, and cached by the file's modification time.
"""

import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.data.storage import frame_path

_MAX_CACHE = 512


class PriceBook:
    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = storage_dir
        self._cache: dict[tuple[Any, ...], Any] = {}
        self._lock = threading.Lock()

    def _path(self, dataset_id: str, kind: str) -> Path:
        return frame_path(self.storage_dir, dataset_id, kind)  # type: ignore[arg-type]

    def _memo(self, key: tuple[Any, ...], make: Any) -> Any:
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        value = make()
        with self._lock:
            if len(self._cache) >= _MAX_CACHE:
                self._cache.clear()
            self._cache[key] = value
        return value

    def _stamp(self, dataset_id: str, kind: str) -> int:
        try:
            return self._path(dataset_id, kind).stat().st_mtime_ns
        except OSError as e:
            raise LookupError(f"Dataset {dataset_id} has no {kind} data") from e

    # ---- underlying --------------------------------------------------------------------------
    def underlying(self, dataset_id: str) -> pd.DataFrame:
        """timestamp (sorted, unique) and close of the underlying."""
        key = ("u", dataset_id, self._stamp(dataset_id, "underlying"))
        return self._memo(  # type: ignore[no-any-return]
            key,
            lambda: (
                pd.read_parquet(self._path(dataset_id, "underlying"), columns=["timestamp", "close"])
                .drop_duplicates("timestamp")
                .sort_values("timestamp")
                .reset_index(drop=True)
            ),
        )

    def timeline(self, dataset_id: str) -> pd.Series:
        return self.underlying(dataset_id)["timestamp"]

    def spot_at(self, dataset_id: str, t: datetime) -> float | None:
        u = self.underlying(dataset_id)
        i = int(u["timestamp"].searchsorted(pd.Timestamp(t), side="right")) - 1
        return round(float(u["close"].iloc[i]), 2) if i >= 0 else None

    # ---- options -----------------------------------------------------------------------------
    def expiries(self, dataset_id: str) -> list[date]:
        key = ("e", dataset_id, self._stamp(dataset_id, "options"))
        found = self._memo(
            key, lambda: pd.read_parquet(self._path(dataset_id, "options"), columns=["expiry"])["expiry"].unique()
        )
        return sorted(pd.Timestamp(e).date() for e in found)

    def listed_expiries(self, dataset_id: str, t: datetime) -> list[date]:
        """Expiries that actually have prices at time t (a contract month is not tradable before it is listed)."""
        return [e for e in self.expiries(dataset_id) if e >= t.date() and not self.chain_at(dataset_id, e, t).empty]

    def series(self, dataset_id: str, expiry: date, strike: float, option_type: str) -> pd.DataFrame:
        """All candles of one contract: timestamp (sorted) and close."""
        key = ("s", dataset_id, self._stamp(dataset_id, "options"), expiry, float(strike), option_type)
        filters = [
            ("expiry", "==", pd.Timestamp(expiry)),
            ("strike", "==", float(strike)),
            ("option_type", "==", option_type),
        ]
        return self._memo(  # type: ignore[no-any-return]
            key,
            lambda: (
                pd.read_parquet(self._path(dataset_id, "options"), columns=["timestamp", "close"], filters=filters)
                .drop_duplicates("timestamp")
                .sort_values("timestamp")
                .reset_index(drop=True)
            ),
        )

    def price_at(self, dataset_id: str, expiry: date, strike: float, option_type: str, t: datetime) -> float | None:
        """Last close at or before t; None if the contract has no candle yet."""
        s = self.series(dataset_id, expiry, strike, option_type)
        i = int(s["timestamp"].searchsorted(pd.Timestamp(t), side="right")) - 1
        return round(float(s["close"].iloc[i]), 2) if i >= 0 else None

    def chain_at(self, dataset_id: str, expiry: date, t: datetime) -> pd.DataFrame:
        """strike, option_type, close for every contract of an expiry at the candle at the clock time."""
        stamp = self._stamp(dataset_id, "options")
        ts = pd.Timestamp(t)
        key = ("c", dataset_id, stamp, expiry, ts)
        filters = [("expiry", "==", pd.Timestamp(expiry)), ("timestamp", "==", ts)]
        return self._memo(  # type: ignore[no-any-return]
            key,
            lambda: pd.read_parquet(
                self._path(dataset_id, "options"), columns=["strike", "option_type", "close"], filters=filters
            ).sort_values(["strike", "option_type"]),
        )


_BOOKS: dict[str, PriceBook] = {}


def get_book(storage_dir: str) -> PriceBook:
    if storage_dir not in _BOOKS:
        _BOOKS[storage_dir] = PriceBook(storage_dir)
    return _BOOKS[storage_dir]
