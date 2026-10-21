from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DatasetKind = Literal["underlying", "options"]
_BOTH: tuple[Literal["CE", "PE"], ...] = ("CE", "PE")


class ColumnMapping(BaseModel):
    """Maps source file columns to the standard schema. Values are source column names."""

    timestamp: str
    open: str
    high: str
    low: str
    close: str
    volume: str | None = None
    symbol: str | None = Field(None, description="Underlying candles only; defaults to dataset underlying")
    underlying: str | None = Field(None, description="Option candles only; defaults to dataset underlying")
    expiry: str | None = Field(None, description="Option candles: required")
    strike: str | None = Field(None, description="Option candles: required")
    option_type: str | None = Field(None, description="Option candles: required (CE/PE/CALL/PUT/C/P)")
    oi: str | None = None
    timestamp_format: str | None = Field(None, description="strptime format; inferred if omitted")
    timezone: str = Field("Asia/Kolkata", description="Applied to naive timestamps; stored as naive local time")

    @classmethod
    def standard(cls, kind: DatasetKind) -> "ColumnMapping":
        base = {f: f for f in ("timestamp", "open", "high", "low", "close", "volume")}
        if kind == "underlying":
            return cls(**base, symbol="symbol")
        return cls(
            **base,
            underlying="underlying",
            expiry="expiry",
            strike="strike",
            option_type="option_type",
            oi="oi",
        )


class GapSample(BaseModel):
    start: datetime
    end: datetime
    missing_candles: int


class QualityReport(BaseModel):
    input_rows: int
    rows: int
    bad_timestamps: int
    bad_rows: int
    invalid_ohlc_rows: int
    duplicates_removed: int
    trading_days: int
    timeframe_minutes: int | None
    missing_candles: int
    gap_count: int
    gap_samples: list[GapSample]
    warnings: list[str]


class DatasetOut(BaseModel):
    id: str
    name: str
    underlying: str
    lot_size: int
    timeframe_minutes: int | None
    start_date: date | None
    end_date: date | None
    underlying_rows: int
    options_rows: int
    expiries: list[date]
    strikes: list[float]
    quality: dict[str, QualityReport]
    created_at: datetime


class UpstoxImportRequest(BaseModel):
    name: str | None = None
    underlying: Literal["NIFTY", "BANKNIFTY"] = "NIFTY"
    start_date: date
    end_date: date
    interval_minutes: Literal[1, 3, 5, 15, 30] = 5
    include_options: bool = Field(False, description="Needs Upstox Plus; only expiries from the last ~6 months exist")
    n_strikes: int = Field(10, ge=1, le=30, description="Strikes on each side of ATM")
    dataset_id: str | None = Field(None, description="Attach to an existing dataset")


class UpstoxExportRequest(BaseModel):
    underlying: Literal["NIFTY", "BANKNIFTY"] = "NIFTY"
    start_date: date
    end_date: date
    interval_minutes: Literal[1, 3, 5, 15, 30] = 1
    include_options: bool = Field(True, description="Needs Upstox Plus; only expiries from the last ~6 months exist")
    n_strikes: int = Field(10, ge=1, le=30, description="Strikes on each side of ATM")
    option_types: list[Literal["CE", "PE"]] = Field(default_factory=lambda: list(_BOTH), min_length=1)
    expiry_type: Literal["all", "weekly", "monthly"] = "all"
    last_expiries: int | None = Field(None, ge=1, description="Only the most recent N expiries in the range")


class ExportJobOut(BaseModel):
    id: str
    status: Literal["running", "done", "failed"]
    underlying: str
    interval: int
    start: date
    end: date
    out_dir: str
    total_expiries: int
    done_expiries: int
    files: list[str]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class SyntheticRequest(BaseModel):
    name: str | None = None
    underlying: str = "NIFTY"
    start_date: date = date(2024, 1, 1)
    trading_days: int = Field(20, ge=1, le=250)
    start_price: float = Field(22000.0, gt=0)
    strike_step: float = Field(50.0, gt=0)
    n_strikes: int = Field(10, ge=1, le=50, description="Strikes on each side of ATM")
    lot_size: int = Field(75, ge=1)
    seed: int = 42
