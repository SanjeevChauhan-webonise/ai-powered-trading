from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ExitReason = Literal["stop_loss", "target", "trailing_sl", "signal", "square_off", "end_of_data"]


class TradeCandle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


class CheckLine(BaseModel):
    """One figure of a trade: what the engine reported next to an independent recomputation."""

    name: str
    reported: float | None = None
    recomputed: float | None = None
    ok: bool
    note: str = ""


class BacktestTrade(BaseModel):
    id: int
    side: Literal["buy", "sell"]
    option_type: Literal["CE", "PE"]
    expiry: date
    strike: float
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry_price: float = Field(description="Fill price incl. slippage")
    exit_price: float = Field(description="Fill price incl. slippage")
    qty: int
    gross_pnl: float = Field(description="(exit-entry) fill prices x qty, sign by side; includes slippage")
    slippage_cost: float = Field(description="Informational: slippage already embedded in gross_pnl")
    brokerage: float
    taxes: float
    net_pnl: float
    exit_reason: ExitReason
    # audit trail: everything needed to re-do this trade by hand
    lots: int | None = None
    lot_size: int | None = None
    entry_raw: float | None = Field(None, description="Option open at the entry candle, before slippage")
    exit_raw: float | None = Field(None, description="Price the exit rule fired at, before slippage")
    stop_price: float | None = None
    target_price: float | None = None
    trail_stop_price: float | None = Field(None, description="Trailing stop level in force when the trade closed")
    candles: list[TradeCandle] = Field(default_factory=list, description="Option candles from entry to exit")
    verified: bool | None = Field(None, description="True when every check line matches the recomputation")
    checks: list[CheckLine] = Field(default_factory=list)


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class DailyPnl(BaseModel):
    date: date
    pnl: float
    trades: int


class BacktestMetrics(BaseModel):
    total_pnl: float
    num_trades: int
    win_rate_pct: float | None
    avg_win: float | None
    avg_loss: float | None
    profit_factor: float | None
    max_drawdown: float
    max_drawdown_pct: float
    sharpe: float | None
    expectancy: float | None
    best_trade: float | None
    worst_trade: float | None
    total_costs: float
    daily_pnl: list[DailyPnl]


class EngineEvent(BaseModel):
    timestamp: datetime
    kind: Literal["missing_option_candle", "no_contract", "skipped_entry"]
    message: str


class Verification(BaseModel):
    checked: int
    passed: int
    failed: int
    sum_of_trades: float
    reported_total_pnl: float
    totals_match: bool
    failed_trade_ids: list[int] = Field(default_factory=list)


class BacktestResult(BaseModel):
    strategy_name: str
    start: date | None
    end: date | None
    capital: float
    lot_size: int
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    metrics: BacktestMetrics
    events: list[EngineEvent]
    events_truncated: bool = False
    verification: Verification | None = None
