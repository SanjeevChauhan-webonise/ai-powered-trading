"""Export Upstox history to CSV (one options file per expiry) and run it as a background job."""

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from app.data.upstox import UpstoxClient, fetch_expiry_options, fetch_underlying, list_expiries

log = logging.getLogger(__name__)

JobStatus = Literal["running", "done", "failed"]


@dataclass
class ExportJob:
    id: str
    underlying: str
    interval: int
    start: date
    end: date
    out_dir: str
    status: JobStatus = "running"
    total_expiries: int = 0
    done_expiries: int = 0
    files: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


def export_range(
    client: UpstoxClient,
    underlying: str,
    interval: int,
    start: date,
    end: date,
    out_dir: Path,
    *,
    n_strikes: int = 10,
    option_types: tuple[str, ...] = ("CE", "PE"),
    expiry_type: str = "all",
    last_expiries: int | None = None,
    include_options: bool = True,
    on_progress: Callable[[ExportJob | None, str], None] | None = None,
    job: ExportJob | None = None,
) -> list[Path]:
    """Write underlying.csv and options_<expiry>.csv under out_dir. Existing files are skipped (resume)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def note(msg: str) -> None:
        log.info(msg)
        if on_progress:
            on_progress(job, msg)

    under_path = out_dir / "underlying.csv"
    if under_path.exists():
        under = pd.read_csv(under_path, parse_dates=["timestamp"])
        note(f"using existing {under_path.name}")
    else:
        under = fetch_underlying(client, underlying, interval, start, end)
        under.to_csv(under_path, index=False)
        written.append(under_path)
        note(f"wrote {under_path.name} ({len(under)} rows)")
    if not include_options:
        return written

    expiries = list_expiries(client, underlying, start, end, last_expiries)
    if job:
        job.total_expiries = len(expiries)
    for i, expiry in enumerate(expiries, 1):
        path = out_dir / f"options_{expiry.isoformat()}.csv"
        if path.exists():
            note(f"[{i}/{len(expiries)}] {path.name} exists, skipping")
        else:
            df, _ = fetch_expiry_options(
                client, underlying, under, expiry, interval, start, n_strikes, option_types, expiry_type
            )
            if df is None:
                note(f"[{i}/{len(expiries)}] {expiry}: no data")
            else:
                df["expiry"] = df["expiry"].dt.date
                df.to_csv(path, index=False)
                written.append(path)
                note(f"[{i}/{len(expiries)}] wrote {path.name} ({len(df)} rows)")
        if job:
            job.done_expiries = i
    return written


_JOBS: dict[str, ExportJob] = {}  # in-memory; files on disk make a re-run resume where it stopped


def get_job(job_id: str) -> ExportJob | None:
    return _JOBS.get(job_id)


def list_jobs() -> list[ExportJob]:
    return sorted(_JOBS.values(), key=lambda j: j.started_at, reverse=True)


def start_job(
    client: UpstoxClient,
    underlying: str,
    interval: int,
    start: date,
    end: date,
    root: Path,
    *,
    n_strikes: int,
    include_options: bool,
    option_types: tuple[str, ...] = ("CE", "PE"),
    expiry_type: str = "all",
    last_expiries: int | None = None,
) -> ExportJob:
    out_dir = root / underlying / f"{interval}m"
    job = ExportJob(uuid.uuid4().hex, underlying, interval, start, end, str(out_dir))
    _JOBS[job.id] = job

    def run() -> None:
        try:
            export_range(
                client, underlying, interval, start, end, out_dir,
                n_strikes=n_strikes, include_options=include_options, option_types=option_types,
                expiry_type=expiry_type, last_expiries=last_expiries, job=job,
            )  # fmt: skip
            job.status = "done"
        except Exception as e:  # recorded on the job; the thread must not die silently
            log.exception("export job %s failed", job.id)
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
        job.files = sorted(p.name for p in out_dir.glob("*.csv"))
        job.finished_at = datetime.now(UTC)

    threading.Thread(target=run, name=f"export-{job.id[:8]}", daemon=True).start()
    return job
