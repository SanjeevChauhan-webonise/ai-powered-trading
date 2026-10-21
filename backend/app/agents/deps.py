from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.news.feeds import NewsFetcher
from app.rag.embeddings import Embedder
from app.rag.store import VectorStore
from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec

RunEngine = Callable[[StrategySpec, date | None, date | None], BacktestResult]


@dataclass(frozen=True)
class Canonical:
    """The exact backtest the pipeline decided on. The backtest agent may not change any of it."""

    spec: StrategySpec
    dataset_id: str
    start: date | None
    end: date | None


@dataclass
class AgentDeps:
    store: VectorStore
    embedder: Embedder
    news: NewsFetcher | None = None
    dataset_timeframe_minutes: int | None = None
    dataset_summary: str = ""
    canonical: Canonical | None = None
    run_engine: RunEngine | None = None
    result: BacktestResult | None = field(default=None)  # set by the run_backtest tool
