from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core import models as core_models  # noqa: F401
from app.core.config import Settings
from app.core.db import Base
from app.data import models  # noqa: F401
from app.data.csv_loader import load_export_dir
from upstox.export import export_range
from upstox.tests.test_upstox import _client


def test_export_then_load_roundtrip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    db_session = Session(engine)
    folder = tmp_path / "NIFTY" / "5m"
    export_range(_client(), "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 17), folder, n_strikes=1)
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
