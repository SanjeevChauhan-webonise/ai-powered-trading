from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core import models as core_models  # noqa: F401
from app.core.config import Settings
from app.core.db import Base
from app.data import models  # noqa: F401
from app.data.csv_loader import load_export_dir
from app.data.export import export_range
from tests.test_upstox import _client


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
