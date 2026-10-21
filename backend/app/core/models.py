from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # stored lower-case
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[str] = mapped_column(String(12), default="beginner")  # beginner | advanced | expert
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuthSession(Base):
    """A login. Only the SHA-256 of the bearer token is stored, so a leaked table cannot be replayed."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(32), index=True)
    strategy_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(200))
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)  # snapshot: later strategy edits never change past runs
    start: Mapped[date | None] = mapped_column(Date, nullable=True)
    end: Mapped[date | None] = mapped_column(Date, nullable=True)
    capital: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))  # completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    total_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    num_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class PipelineRun(Base):
    """One multi-agent run: research -> strategy -> backtest -> risk review. Steps are updated as it progresses."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20))  # queued | running | completed | failed
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    backtest_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class PaperAccount(Base):
    """One simulated trading account per user. The market clock replays a dataset; nothing here touches a broker."""

    __tablename__ = "paper_accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    starting_balance: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    dataset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # the dataset the clock replays
    clock_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class _Contract:
    """Columns that identify an option contract in a dataset."""

    dataset_id: Mapped[str] = mapped_column(String(32))
    underlying: Mapped[str] = mapped_column(String(50))
    expiry: Mapped[date] = mapped_column(Date)
    strike: Mapped[float] = mapped_column(Float)
    option_type: Mapped[str] = mapped_column(String(2))  # CE | PE


class PaperPosition(_Contract, Base):
    """An open long option position (selling to open is not supported)."""

    __tablename__ = "paper_positions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    avg_price: Mapped[float] = mapped_column(Float)
    stop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # % of entry premium
    target_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    square_off: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM": forced intraday exit
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # the AI run whose plan opened it
    opened_at: Mapped[datetime] = mapped_column(DateTime)  # market-clock time
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PaperOrder(_Contract, Base):
    __tablename__ = "paper_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10))  # filled | rejected
    source: Mapped[str] = mapped_column(String(10))  # manual | plan | auto (stop, target, square-off, expiry)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime)  # market-clock time
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class PaperTrade(_Contract, Base):
    """A closed (or partly closed) position with its realised P&L."""

    __tablename__ = "paper_trades"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime)
    exit_time: Mapped[datetime] = mapped_column(DateTime)
    gross_pnl: Mapped[float] = mapped_column(Float)
    costs: Mapped[float] = mapped_column(Float)  # brokerage for both legs + taxes
    net_pnl: Mapped[float] = mapped_column(Float)
    exit_reason: Mapped[str] = mapped_column(String(12))  # manual | stop | target | squareoff | expiry
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
