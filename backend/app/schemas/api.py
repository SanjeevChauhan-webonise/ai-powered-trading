from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    spec: StrategySpec


class ValidateRequest(BaseModel):
    spec: dict[str, Any] = Field(description="Raw strategy spec JSON to validate")


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list, description="'path: message' per problem")
    spec: StrategySpec | None = Field(None, description="Normalized spec (defaults filled) when valid")


class StrategyCreate(BaseModel):
    name: str | None = Field(None, description="Defaults to spec.name")
    spec: StrategySpec


class StrategyOut(BaseModel):
    id: str
    name: str
    spec: StrategySpec
    created_at: datetime


class BacktestRequest(BaseModel):
    dataset_id: str
    strategy_id: str | None = None
    template_id: str | None = None
    spec: StrategySpec | None = None
    start: date | None = None
    end: date | None = None
    capital: float = Field(100_000.0, gt=0)

    @model_validator(mode="after")
    def _check(self) -> "BacktestRequest":
        if sum(x is not None for x in (self.strategy_id, self.template_id, self.spec)) != 1:
            raise ValueError("Provide exactly one of strategy_id, template_id, spec")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class BacktestRunSummary(BaseModel):
    id: str
    dataset_id: str
    strategy_id: str | None
    strategy_name: str
    start: date | None
    end: date | None
    capital: float
    status: Literal["completed", "failed"]
    total_pnl: float | None
    num_trades: int | None
    created_at: datetime


class BacktestRunOut(BacktestRunSummary):
    spec: StrategySpec
    error: str | None
    result: BacktestResult | None
