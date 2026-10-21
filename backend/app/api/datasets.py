import json
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import Cfg, Db
from app.data import export, service, upstox
from app.data.models import Dataset
from app.data.normalize import DataError
from app.data.synthetic import SyntheticConfig, generate
from app.schemas.data import (
    ColumnMapping,
    DatasetKind,
    DatasetOut,
    ExportJobOut,
    SyntheticRequest,
    UpstoxExportRequest,
    UpstoxImportRequest,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _read_upload(file: UploadFile) -> pd.DataFrame:
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(file.file)
        if name.endswith(".parquet"):
            return pd.read_parquet(file.file)
    except Exception as e:
        raise DataError(f"Could not read file: {e}") from e
    raise DataError("Only .csv and .parquet files are supported")


def _out(row: Dataset) -> DatasetOut:
    return DatasetOut.model_validate(row, from_attributes=True)


@router.post("/upload", response_model=DatasetOut, summary="Upload CSV/Parquet with a column mapping")
def upload_dataset(
    db: Db,
    settings: Cfg,
    file: Annotated[UploadFile, File(description=".csv or .parquet")],
    mapping: Annotated[str, Form(description="JSON ColumnMapping: standard field -> source column name")],
    kind: Annotated[DatasetKind, Form()],
    underlying: Annotated[str, Form()],
    lot_size: Annotated[int, Form(ge=1)] = 1,
    name: Annotated[str | None, Form()] = None,
    dataset_id: Annotated[
        str | None,
        Form(description="Attach to an existing dataset (e.g. add options to underlying)"),
    ] = None,
    resample_to: Annotated[int | None, Form(ge=2, description="Resample to N-minute candles")] = None,
) -> DatasetOut:
    try:
        col_map = ColumnMapping.model_validate(json.loads(mapping))
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(422, f"Invalid mapping: {e}") from e
    try:
        row = service.ingest(
            db, settings, _read_upload(file), kind=kind, mapping=col_map, underlying=underlying,
            lot_size=lot_size, name=name, dataset_id=dataset_id, resample_to=resample_to,
        )  # fmt: skip
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except DataError as e:
        raise HTTPException(400, str(e)) from e
    return _out(row)


@router.post("/synthetic", response_model=DatasetOut, summary="Generate a synthetic demo dataset")
def create_synthetic(req: SyntheticRequest, db: Db, settings: Cfg) -> DatasetOut:
    cfg = SyntheticConfig(
        underlying=req.underlying, start_date=req.start_date, trading_days=req.trading_days,
        start_price=req.start_price, strike_step=req.strike_step, n_strikes=req.n_strikes, seed=req.seed,
    )  # fmt: skip
    under, opts = generate(cfg)
    row = service.ingest(
        db, settings, under, kind="underlying", mapping=ColumnMapping.standard("underlying"),
        underlying=req.underlying, lot_size=req.lot_size, name=req.name or f"Synthetic {req.underlying}",
    )  # fmt: skip
    row = service.ingest(
        db, settings, opts, kind="options", mapping=ColumnMapping.standard("options"),
        underlying=req.underlying, dataset_id=row.id,
    )  # fmt: skip
    return _out(row)


@router.post("/upstox", response_model=DatasetOut, summary="Import NIFTY/BANKNIFTY history from Upstox")
def import_upstox(req: UpstoxImportRequest, db: Db, settings: Cfg) -> DatasetOut:
    if req.end_date < req.start_date:
        raise HTTPException(422, "end_date must not be before start_date")
    try:
        client = upstox.UpstoxClient(settings.upstox_access_token)
        under = upstox.fetch_underlying(client, req.underlying, req.interval_minutes, req.start_date, req.end_date)
        opts, lot_size = None, 1
        if req.include_options:
            opts, lot_size = upstox.fetch_options(
                client, req.underlying, under, req.interval_minutes, req.start_date, req.end_date, req.n_strikes
            )  # fmt: skip
        row = service.ingest(
            db, settings, under, kind="underlying", mapping=ColumnMapping.standard("underlying"),
            underlying=req.underlying, lot_size=lot_size, name=req.name or f"Upstox {req.underlying}",
            dataset_id=req.dataset_id,
        )  # fmt: skip
        if opts is not None:
            row = service.ingest(
                db, settings, opts, kind="options", mapping=ColumnMapping.standard("options"),
                underlying=req.underlying, dataset_id=row.id,
            )  # fmt: skip
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except upstox.UpstoxError as e:
        raise HTTPException(502, str(e)) from e
    except DataError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach Upstox: {e}") from e
    return _out(row)


def _job_out(j: export.ExportJob) -> ExportJobOut:
    return ExportJobOut.model_validate(j, from_attributes=True)


@router.post("/upstox/export-jobs", response_model=ExportJobOut, summary="Start a background CSV export from Upstox")
def start_export_job(req: UpstoxExportRequest, settings: Cfg) -> ExportJobOut:
    """Writes one options CSV per expiry under <storage_dir>/exports/<underlying>/<N>m/; re-running resumes."""
    if req.end_date < req.start_date:
        raise HTTPException(422, "end_date must not be before start_date")
    try:
        client = upstox.UpstoxClient(settings.upstox_access_token)
    except upstox.UpstoxError as e:
        raise HTTPException(400, str(e)) from e
    job = export.start_job(
        client, req.underlying, req.interval_minutes, req.start_date, req.end_date,
        Path(settings.storage_dir) / "exports", n_strikes=req.n_strikes, include_options=req.include_options,
        option_types=tuple(req.option_types), expiry_type=req.expiry_type, last_expiries=req.last_expiries,
    )  # fmt: skip
    return _job_out(job)


@router.get("/upstox/export-jobs", response_model=list[ExportJobOut], summary="List export jobs")
def list_export_jobs() -> list[ExportJobOut]:
    return [_job_out(j) for j in export.list_jobs()]


@router.get("/upstox/export-jobs/{job_id}", response_model=ExportJobOut, summary="Export job progress")
def get_export_job(job_id: str) -> ExportJobOut:
    job = export.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Export job not found")
    return _job_out(job)


@router.get("", response_model=list[DatasetOut], summary="List datasets")
def list_datasets(db: Db) -> list[DatasetOut]:
    rows = db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()
    return [_out(r) for r in rows]


@router.get("/{dataset_id}", response_model=DatasetOut, summary="Dataset details and quality report")
def get_dataset(dataset_id: str, db: Db) -> DatasetOut:
    row = db.get(Dataset, dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    return _out(row)
