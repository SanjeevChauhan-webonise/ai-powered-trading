"""Declarative strategy spec. Pure data: strategies are never executed as code."""

from collections.abc import Iterator
from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engine.indicators import REGISTRY, resolve_params

IndicatorType = Literal["ema", "sma", "rsi", "macd", "bollinger", "atr", "vwap", "supertrend"]
Op = Literal["crosses_above", "crosses_below", ">", "<", "between"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IndicatorSpec(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", description="Referenced by rules")
    type: IndicatorType
    params: dict[str, float] = Field(default_factory=dict, description="e.g. {'period': 14}; defaults apply")


class IndicatorRef(_Strict):
    indicator: str
    output: str | None = Field(None, description="Indicator output column (e.g. 'signal' for macd)")


class PriceRef(_Strict):
    price: Literal["open", "high", "low", "close"]


class ValueRef(_Strict):
    value: float


class RangeRef(_Strict):
    range: tuple[float, float]


Operand = IndicatorRef | PriceRef | ValueRef | RangeRef


class Rule(_Strict):
    left: Operand
    op: Op
    right: Operand

    @model_validator(mode="after")
    def _check(self) -> "Rule":
        if isinstance(self.left, RangeRef):
            raise ValueError("'range' can only be used as the right operand of 'between'")
        if self.op == "between":
            if not isinstance(self.right, RangeRef) or self.right.range[0] > self.right.range[1]:
                raise ValueError("'between' needs right={'range': [low, high]} with low <= high")
        elif isinstance(self.right, RangeRef):
            raise ValueError("'range' is only valid with op 'between'")
        return self


class AllOf(_Strict):
    all: list["Condition"] = Field(min_length=1)


class AnyOf(_Strict):
    any: list["Condition"] = Field(min_length=1)


type Condition = Rule | AllOf | AnyOf

AllOf.model_rebuild()
AnyOf.model_rebuild()


def iter_rules(cond: Condition) -> Iterator[Rule]:
    if isinstance(cond, Rule):
        yield cond
    else:
        for c in cond.all if isinstance(cond, AllOf) else cond.any:
            yield from iter_rules(c)


class StrikeSpec(_Strict):
    mode: Literal["atm", "offset", "nearest_premium"] = "atm"
    offset: int = Field(0, description="mode=offset: strikes above (+) / below (-) ATM, for both CE and PE")
    premium: float | None = Field(None, gt=0, description="mode=nearest_premium: target option premium")

    @model_validator(mode="after")
    def _check(self) -> "StrikeSpec":
        if self.mode == "nearest_premium" and self.premium is None:
            raise ValueError("nearest_premium requires 'premium'")
        return self


_BOTH: tuple[Literal["CE", "PE"], ...] = ("CE", "PE")


class InstrumentSpec(_Strict):
    option_types: list[Literal["CE", "PE"]] = Field(default_factory=lambda: list(_BOTH), min_length=1)
    strike: StrikeSpec = Field(default_factory=StrikeSpec)
    expiry: Literal["nearest_weekly", "monthly"] = "nearest_weekly"


class RiskSpec(_Strict):
    stop_loss_pct: float | None = Field(None, gt=0, description="% of entry premium")
    target_pct: float | None = Field(None, gt=0)
    trailing_sl_pct: float | None = Field(None, gt=0, description="% from best premium since entry")
    max_trades_per_day: int | None = Field(None, ge=1)
    entry_start: time = time(9, 20)
    entry_end: time = time(15, 0)
    square_off: time = Field(time(15, 15), description="Forced intraday exit at this time")

    @model_validator(mode="after")
    def _check(self) -> "RiskSpec":
        if not self.entry_start < self.entry_end <= self.square_off:
            raise ValueError("require entry_start < entry_end <= square_off")
        return self


class SlippageSpec(_Strict):
    mode: Literal["points", "pct"] = "points"
    value: float = Field(0.0, ge=0)


class CostSpec(_Strict):
    brokerage_per_order: float = Field(20.0, ge=0)
    slippage: SlippageSpec = Field(default_factory=SlippageSpec)
    tax_pct: float = Field(0.05, ge=0, description="Approximate taxes/charges, % of turnover (entry + exit)")


class StrategySpec(_Strict):
    name: str
    description: str = ""
    signal_source: Literal["underlying", "option"] = "underlying"
    timeframe_minutes: int | None = Field(None, ge=2, description="Resample data to this timeframe before running")
    indicators: list[IndicatorSpec] = Field(default_factory=list)
    entry_bullish: Condition | None = Field(None, description="Bullish signal: buy CE (or sell PE)")
    entry_bearish: Condition | None = Field(None, description="Bearish signal: buy PE (or sell CE)")
    exit_condition: Condition | None = Field(None, description="Signal-based exit for any open position")
    exit_on_opposite_signal: bool = False
    direction: Literal["buy", "sell"] = "buy"
    instrument: InstrumentSpec = Field(default_factory=InstrumentSpec)
    risk: RiskSpec = Field(default_factory=RiskSpec)
    lots: int = Field(1, ge=1)
    costs: CostSpec = Field(default_factory=CostSpec)

    @model_validator(mode="after")
    def _check(self) -> "StrategySpec":
        if self.signal_source != "underlying":
            raise ValueError("signal_source='option' is not supported yet; use 'underlying'")
        if self.entry_bullish is None and self.entry_bearish is None:
            raise ValueError("Define entry_bullish and/or entry_bearish")
        ids = [i.id for i in self.indicators]
        if len(ids) != len(set(ids)):
            raise ValueError("Indicator ids must be unique")
        for ind in self.indicators:
            resolve_params(ind.type, ind.params)
        by_id = {i.id: i for i in self.indicators}
        for cond in (self.entry_bullish, self.entry_bearish, self.exit_condition):
            for rule in iter_rules(cond) if cond is not None else []:
                for op in (rule.left, rule.right):
                    if isinstance(op, IndicatorRef):
                        if op.indicator not in by_id:
                            raise ValueError(f"Rule references unknown indicator '{op.indicator}'")
                        d = REGISTRY[by_id[op.indicator].type]
                        if op.output is not None and op.output not in d.outputs:
                            raise ValueError(f"Indicator '{op.indicator}' has no output '{op.output}'; use {d.outputs}")
        return self
