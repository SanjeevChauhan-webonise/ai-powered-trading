import logging
from functools import partial

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import Cfg, CurrentUser, Db
from app.api.spec_source import resolve_spec
from app.core.models import BacktestRun
from app.data.backtest_io import build_run_record, load_frames
from app.data.models import Dataset
from app.engine.backtest import run_backtest
from app.engine.lots import LOT_SCHEDULES
from app.schemas.api import BacktestRequest, BacktestRunOut, BacktestRunSummary
from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec

router = APIRouter(prefix="/backtests", tags=["backtests"])
log = logging.getLogger(__name__)


def _summary(r: BacktestRun) -> BacktestRunSummary:
    return BacktestRunSummary.model_validate(r, from_attributes=True)


def _out(r: BacktestRun) -> BacktestRunOut:
    return BacktestRunOut(
        **_summary(r).model_dump(),
        spec=StrategySpec.model_validate(r.spec),
        error=r.error,
        result=BacktestResult.model_validate(r.result) if r.result else None,
    )


@router.post("", response_model=BacktestRunOut, summary="Run a backtest directly (no AI)")
def create_backtest(req: BacktestRequest, db: Db, settings: Cfg, user: CurrentUser) -> BacktestRunOut:
    """Runs synchronously. Engine failures are stored as a run with status 'failed' and an error message."""
    ds = db.get(Dataset, req.dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    if not ds.underlying_rows or not ds.options_rows:
        raise HTTPException(400, "Dataset needs both underlying and option candles")
    spec, strategy_id = resolve_spec(
        db, spec=req.spec, template_id=req.template_id, strategy_id=req.strategy_id, user_id=user.id
    )
    assert spec is not None  # BacktestRequest guarantees exactly one source
    record = partial(
        build_run_record,
        dataset_id=ds.id,
        spec=spec,
        strategy_id=strategy_id,
        user_id=user.id,
        start=req.start,
        end=req.end,
        capital=req.capital,
    )
    try:
        under, opts = load_frames(settings, ds.id)
        result = run_backtest(
            spec, under, opts, lot_size=ds.lot_size, start=req.start, end=req.end, capital=req.capital,
            lot_schedule=LOT_SCHEDULES.get(ds.underlying),
        )  # fmt: skip
        run = record(result=result)
    except Exception as e:  # engine/data problems are recorded, not raised
        log.exception("backtest failed")
        run = record(error=f"{type(e).__name__}: {e}")
    db.add(run)
    db.commit()
    db.refresh(run)
    return _out(run)


@router.get("", response_model=list[BacktestRunSummary], summary="List backtest runs (summaries)")
def list_backtests(db: Db, user: CurrentUser) -> list[BacktestRunSummary]:
    rows = db.scalars(select(BacktestRun).where(BacktestRun.user_id == user.id).order_by(BacktestRun.created_at.desc()))
    return [_summary(r) for r in rows]


@router.get("/{run_id}", response_model=BacktestRunOut, summary="Full backtest result")
def get_backtest(run_id: str, db: Db, user: CurrentUser) -> BacktestRunOut:
    row = db.get(BacktestRun, run_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Backtest not found")
    return _out(row)
