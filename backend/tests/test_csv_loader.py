
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core import models as core_models  # noqa: F401
from app.core.config import Settings
from app.core.db import Base
from app.data import models  # noqa: F401
from app.data.csv_loader import load_export_dir


def _write_export(folder) -> None:
    """One underlying.csv (2 candles) and one options_<expiry>.csv in the layout load_export_dir reads."""
    folder.mkdir(parents=True)
    ts = ["2025-04-10 09:15:00", "2025-04-10 09:20:00"]
    pd.DataFrame(
        {"timestamp": ts, "symbol": "NIFTY", "open": [23000.0, 23010], "high": [23020.0, 23030],
         "low": [22990.0, 23000], "close": [23010.0, 23020], "volume": [100, 120]}
    ).to_csv(folder / "underlying.csv", index=False)
    pd.DataFrame(
        {"timestamp": ts, "underlying": "NIFTY", "expiry": "2025-04-17", "strike": 23000.0, "option_type": "CE",
         "open": [100.0, 101], "high": [102.0, 103], "low": [99.0, 100], "close": [101.0, 102],
         "volume": [10, 12], "oi": [1000.0, 1010]}
    ).to_csv(folder / "options_2025-04-17.csv", index=False)


def test_export_then_load_roundtrip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    db_session = Session(engine)
    folder = tmp_path / "NIFTY" / "5m"
    _write_export(folder)
    # a second expiry file must be added to, not replace, the first
    second = pd.read_csv(folder / "options_2025-04-17.csv").assign(expiry="2025-04-24")
    second.to_csv(folder / "options_2025-04-24.csv", index=False)

    settings = Settings(storage_dir=str(tmp_path / "store"))
    row = load_export_dir(db_session, settings, folder, underlying="NIFTY", lot_size=75)
    assert row.underlying_rows == 2 and row.lot_size == 75
    assert row.expiries == ["2025-04-17", "2025-04-24"]
    assert row.options_rows == 2 * len(second.drop_duplicates(["timestamp", "strike", "option_type"]))


def test_coarsen_options_bins_on_the_clock() -> None:
    from app.data.csv_loader import _coarsen_options

    ts = pd.to_datetime(["2025-01-01 09:15", "2025-01-01 09:16", "2025-01-01 09:19", "2025-01-01 09:20"])
    df = pd.DataFrame(
        {"timestamp": ts, "underlying": "NIFTY", "expiry": pd.Timestamp("2025-01-02"), "strike": 100.0,
         "option_type": "CE", "open": [10.0, 11, 12, 13], "high": [12.0, 14, 13, 15], "low": [9.0, 10, 11, 12],
         "close": [11.0, 12, 13, 14], "volume": [1, 2, 3, 4], "oi": [5.0, 6, 7, 8]}
    )  # fmt: skip
    out = _coarsen_options(df, 5)
    assert list(out["timestamp"]) == list(pd.to_datetime(["2025-01-01 09:15", "2025-01-01 09:20"]))
    first = out.iloc[0]
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"], first["oi"]) == (
        10.0, 14.0, 9.0, 13.0, 6, 7.0
    )  # fmt: skip


def test_coarsen_options_open_and_close_follow_time_not_row_order() -> None:
    """Many shuffled 1-minute rows per bin: open is the earliest minute's open, close the latest minute's close."""
    from app.data.csv_loader import _coarsen_options

    minutes = pd.date_range("2025-01-01 09:15", periods=300, freq="1min")
    df = pd.DataFrame(
        {"timestamp": minutes, "underlying": "NIFTY", "expiry": pd.Timestamp("2025-01-02"), "strike": 100.0,
         "option_type": "CE", "open": np.arange(300, dtype=float), "high": np.arange(300) + 0.5,
         "low": np.arange(300) - 0.5, "close": np.arange(300) + 0.25, "volume": 1, "oi": np.arange(300, dtype=float)}
    ).sample(frac=1.0, random_state=1).reset_index(drop=True)  # fmt: skip
    out = _coarsen_options(df, 5).sort_values("timestamp").reset_index(drop=True)
    assert len(out) == 60
    assert list(out["open"]) == [float(i) for i in range(0, 300, 5)]  # first minute of each bin
    assert list(out["close"]) == [i + 4 + 0.25 for i in range(0, 300, 5)]  # last minute of each bin
    assert list(out["oi"]) == [float(i + 4) for i in range(0, 300, 5)]
    assert (out["volume"] == 5).all()
