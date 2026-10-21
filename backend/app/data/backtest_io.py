import uuid
from datetime import date

import pandas as pd

from app.core.config import Settings
from app.core.models import BacktestRun
from app.data.storage import frame_path, read_frame
from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec


def load_frames(settings: Settings, dataset_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        read_frame(frame_path(settings.storage_dir, dataset_id, "underlying")),
        read_frame(frame_path(settings.storage_dir, dataset_id, "options")),
    )


def build_run_record(
    *,
    dataset_id: str,
    spec: StrategySpec,
    strategy_id: str | None,
    start: date | None,
    end: date | None,
    capital: float,
    user_id: str | None = None,
    result: BacktestResult | None = None,
    error: str | None = None,
) -> BacktestRun:
    """A backtest_runs row: completed when `result` is given, otherwise failed with `error`."""
    return BacktestRun(
        id=uuid.uuid4().hex,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        user_id=user_id,
        strategy_name=spec.name,
        spec=spec.model_dump(mode="json"),
        start=start,
        end=end,
        capital=capital,
        status="completed" if result else "failed",
        error=error,
        result=result.model_dump(mode="json") if result else None,
        total_pnl=result.metrics.total_pnl if result else None,
        num_trades=result.metrics.num_trades if result else None,
    )
