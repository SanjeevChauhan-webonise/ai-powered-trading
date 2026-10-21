from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

OptionType = Literal["CE", "PE"]


class AccountOut(BaseModel):
    starting_balance: float
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: int
    dataset_id: str | None
    dataset_name: str | None
    underlying: str | None
    lot_size: int | None
    clock_time: datetime | None
    clock_end: datetime | None


class PositionOut(BaseModel):
    id: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    qty: int
    lots: int
    avg_price: float
    mark_price: float
    unrealized_pnl: float
    stop_pct: float | None
    target_pct: float | None
    square_off: str | None
    run_id: str | None
    opened_at: datetime


class OrderOut(BaseModel):
    id: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    side: Literal["buy", "sell"]
    qty: int
    price: float
    status: Literal["filled", "rejected"]
    source: str
    note: str | None
    run_id: str | None
    placed_at: datetime


class TradeOut(BaseModel):
    id: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    qty: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    run_id: str | None


class ResetIn(BaseModel):
    starting_balance: float | None = Field(None, gt=0, le=1_000_000_000)


class ClockStartIn(BaseModel):
    dataset_id: str
    at: datetime | None = Field(
        None, description="Start at the first candle on or after this time; default: 3rd-last day"
    )


class AdvanceIn(BaseModel):
    candles: int = Field(1, ge=1, le=2000)


class AdvanceOut(BaseModel):
    account: AccountOut
    exits: list[TradeOut]
    at_end: bool


class OrderIn(BaseModel):
    expiry: date
    strike: float = Field(gt=0)
    option_type: OptionType
    lots: int = Field(1, ge=1, le=200)
    stop_pct: float | None = Field(None, gt=0, le=100, description="% of the entry premium")
    target_pct: float | None = Field(None, gt=0)
    dataset_id: str | None = Field(None, description="Starts the market clock on this dataset if it is not running")


class CloseIn(BaseModel):
    lots: int | None = Field(None, ge=1, description="Lots to sell; default: the whole position")


class FromPlanIn(BaseModel):
    run_id: str
    option_type: OptionType


class FromPlanOut(BaseModel):
    order: OrderOut
    account: AccountOut
    notes: list[str]


class ChainRow(BaseModel):
    strike: float
    ce: float | None
    pe: float | None


class ChainOut(BaseModel):
    dataset_id: str
    underlying: str
    expiry: date
    clock_time: datetime
    spot: float | None
    lot_size: int
    rows: list[ChainRow]


class ExpiriesOut(BaseModel):
    dataset_id: str
    clock_time: datetime
    expiries: list[date]
