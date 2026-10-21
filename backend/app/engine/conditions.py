import numpy as np
import pandas as pd

from app.engine import indicators
from app.schemas.strategy import (
    AllOf,
    Condition,
    IndicatorRef,
    IndicatorSpec,
    Operand,
    PriceRef,
    RangeRef,
    Rule,
    ValueRef,
)

Frames = dict[str, pd.DataFrame]


def compute_indicators(specs: list[IndicatorSpec], df: pd.DataFrame) -> Frames:
    return {s.id: indicators.compute(s.type, df, s.params) for s in specs}


def _series(op: Operand, frames: Frames, df: pd.DataFrame, types: dict[str, str]) -> pd.Series:
    if isinstance(op, IndicatorRef):
        out = op.output or indicators.REGISTRY[types[op.indicator]].default_output
        return frames[op.indicator][out]
    if isinstance(op, PriceRef):
        return df[op.price]
    if isinstance(op, ValueRef):
        return pd.Series(op.value, index=df.index, dtype=float)
    raise TypeError("range operand is only valid on the right of 'between'")


def evaluate(cond: Condition, frames: Frames, df: pd.DataFrame, types: dict[str, str]) -> pd.Series:
    """Boolean Series, True where the condition holds on that candle's close. NaN compares False."""
    if isinstance(cond, Rule):
        left = _series(cond.left, frames, df, types)
        if cond.op == "between":
            assert isinstance(cond.right, RangeRef)
            lo, hi = cond.right.range
            return (left >= lo) & (left <= hi)
        right = _series(cond.right, frames, df, types)
        if cond.op == ">":
            return left > right
        if cond.op == "<":
            return left < right
        if cond.op == "crosses_above":
            return (left.shift() <= right.shift()) & (left > right)
        return (left.shift() >= right.shift()) & (left < right)
    parts = [evaluate(c, frames, df, types) for c in (cond.all if isinstance(cond, AllOf) else cond.any)]
    stacked = np.vstack([p.to_numpy() for p in parts])
    res = stacked.all(axis=0) if isinstance(cond, AllOf) else stacked.any(axis=0)
    return pd.Series(res, index=df.index)
