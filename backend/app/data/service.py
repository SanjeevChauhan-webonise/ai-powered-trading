import logging
import uuid

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.data.models import Dataset
from app.data.normalize import DataError, normalize
from app.data.resample import resample
from app.data.storage import frame_path, read_frame, write_frame
from app.data.validate import build_report, infer_timeframe_minutes
from app.schemas.data import ColumnMapping, DatasetKind

log = logging.getLogger(__name__)


def ingest(
    session: Session,
    settings: Settings,
    raw: pd.DataFrame,
    *,
    kind: DatasetKind,
    mapping: ColumnMapping,
    underlying: str,
    lot_size: int = 1,
    name: str | None = None,
    dataset_id: str | None = None,
    resample_to: int | None = None,
) -> Dataset:
    """Normalize + validate + store one file. Pass dataset_id to attach to an existing dataset."""
    row = session.get(Dataset, dataset_id) if dataset_id else None
    if dataset_id and row is None:
        raise LookupError(f"Dataset {dataset_id} not found")
    if row is not None and row.underlying != underlying:
        raise DataError(f"Dataset underlying is '{row.underlying}', got '{underlying}'")

    df, stats = normalize(raw, kind, mapping, underlying)
    report = build_report(df, stats)
    if resample_to:
        df = resample(df, kind, resample_to)

    if row is None:
        row = Dataset(id=uuid.uuid4().hex, name=name or underlying, underlying=underlying, lot_size=lot_size)
    write_frame(frame_path(settings.storage_dir, row.id, kind), df)
    row.quality = {**(row.quality or {}), kind: report.model_dump(mode="json")}
    _refresh_meta(row, settings)
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("ingested %s rows of %s into dataset %s", len(df), kind, row.id)
    return row


def _refresh_meta(row: Dataset, settings: Settings) -> None:
    up = frame_path(settings.storage_dir, row.id, "underlying")
    op = frame_path(settings.storage_dir, row.id, "options")
    under = read_frame(up, ["timestamp"]) if up.exists() else None
    opts = read_frame(op, ["timestamp", "expiry", "strike"]) if op.exists() else None
    frames = [f["timestamp"] for f in (under, opts) if f is not None]
    all_ts = pd.concat(frames)
    row.start_date = all_ts.min().date()
    row.end_date = all_ts.max().date()
    row.underlying_rows = len(under) if under is not None else 0
    row.options_rows = len(opts) if opts is not None else 0
    primary = under if under is not None else opts
    assert primary is not None
    row.timeframe_minutes = infer_timeframe_minutes(primary["timestamp"])
    if opts is not None:
        row.expiries = sorted(e.date().isoformat() for e in opts["expiry"].unique())
        row.strikes = sorted(float(s) for s in opts["strike"].unique())
