"""Load an export folder (underlying.csv + options_<expiry>.csv files) into one dataset."""

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.data import service
from app.data.models import Dataset
from app.data.normalize import DataError
from app.schemas.data import ColumnMapping


def load_export_dir(
    session: Session,
    settings: Settings,
    folder: Path,
    *,
    underlying: str,
    lot_size: int,
    name: str | None = None,
    dataset_id: str | None = None,
) -> Dataset:
    """Ingest <folder>/underlying.csv, then every options_*.csv as a single options frame.

    Options files are concatenated before ingesting: ingest() replaces the dataset's options data,
    so loading expiry files one by one would keep only the last one.
    """
    under_path = folder / "underlying.csv"
    if not under_path.exists():
        raise DataError(f"{under_path} not found")
    row = service.ingest(
        session, settings, pd.read_csv(under_path), kind="underlying",
        mapping=ColumnMapping.standard("underlying"), underlying=underlying, lot_size=lot_size,
        name=name or f"{underlying} {folder.name}", dataset_id=dataset_id,
    )  # fmt: skip
    files = sorted(folder.glob("options_*.csv"))
    if files:
        opts = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
        row = service.ingest(
            session, settings, opts, kind="options", mapping=ColumnMapping.standard("options"),
            underlying=underlying, dataset_id=row.id,
        )  # fmt: skip
    return row
