"""Load an export folder (underlying.csv + options_<expiry>.csv files) into one dataset."""

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.data import service
from app.data.models import Dataset
from app.data.normalize import DataError, normalize
from app.schemas.data import ColumnMapping


def _coarsen_options(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate one expiry's candles to `minutes`, with bins on the clock (09:15 is a multiple of 5/15/...)."""
    df = df.assign(timestamp=df["timestamp"].dt.floor(f"{minutes}min"))
    agg: dict[str, str] = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if "oi" in df.columns:
        agg["oi"] = "last"
    keys = ["underlying", "expiry", "strike", "option_type", "timestamp"]
    return df.sort_values("timestamp").groupby(keys, sort=False, as_index=False).agg(agg)


def load_export_dir(
    session: Session,
    settings: Settings,
    folder: Path,
    *,
    underlying: str,
    lot_size: int,
    name: str | None = None,
    dataset_id: str | None = None,
    resample_to: int | None = None,
) -> Dataset:
    """Ingest <folder>/underlying.csv, then every options_*.csv as a single options frame.

    resample_to coarsens the candles (e.g. 1-minute -> 5) one expiry file at a time, so a multi-year 1-minute
    export fits in memory.

    Options files are concatenated before ingesting: ingest() replaces the dataset's options data,
    so loading expiry files one by one would keep only the last one.
    """
    under_path = folder / "underlying.csv"
    if not under_path.exists():
        raise DataError(f"{under_path} not found")
    row = service.ingest(
        session, settings, pd.read_csv(under_path), kind="underlying",
        mapping=ColumnMapping.standard("underlying"), underlying=underlying, lot_size=lot_size,
        name=name or f"{underlying} {folder.name}", dataset_id=dataset_id, resample_to=resample_to,
    )  # fmt: skip
    files = sorted(folder.glob("options_*.csv"))
    if files:
        if resample_to:
            mapping = ColumnMapping.standard("options")
            parts = (normalize(pd.read_csv(f), "options", mapping, underlying)[0] for f in files)
            opts = pd.concat((_coarsen_options(p, resample_to) for p in parts), ignore_index=True)
        else:
            opts = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
        row = service.ingest(
            session, settings, opts, kind="options", mapping=ColumnMapping.standard("options"),
            underlying=underlying, dataset_id=row.id,
        )  # fmt: skip
    return row
