"""Deterministic sanity facts about a StrategySpec, computed in code and handed to the Verify agent.

The agent judges and explains these; it never computes numbers itself.
"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.strategy import (
    Condition,
    IndicatorRef,
    RangeRef,
    StrategySpec,
    ValueRef,
    iter_rules,
)

Severity = Literal["low", "medium", "high"]

HIGH_STOP_LOSS_PCT = 50.0
MIN_REWARD_TO_RISK = 1.0


class SpecFlag(BaseModel):
    code: str
    severity: Severity
    message: str


class SpecFacts(BaseModel):
    sides: list[Literal["bullish", "bearish"]]
    indicators: list[str]
    unused_indicators: list[str]
    has_stop_loss: bool
    has_target: bool
    has_trailing_sl: bool
    has_signal_exit: bool
    reward_to_risk: float | None
    entry_window_minutes: int
    flags: list[SpecFlag]


def _conditions(spec: StrategySpec) -> list[Condition]:
    return [c for c in (spec.entry_bullish, spec.entry_bearish, spec.exit_condition) if c is not None]


def check_spec(spec: StrategySpec) -> SpecFacts:
    rules = [r for c in _conditions(spec) for r in iter_rules(c)]
    used = {o.indicator for r in rules for o in (r.left, r.right) if isinstance(o, IndicatorRef)}
    by_id = {i.id: i for i in spec.indicators}
    unused = [i.id for i in spec.indicators if i.id not in used]
    r = spec.risk
    has_signal_exit = spec.exit_condition is not None or spec.exit_on_opposite_signal
    rr = round(r.target_pct / r.stop_loss_pct, 2) if r.target_pct and r.stop_loss_pct else None
    window = (r.entry_end.hour * 60 + r.entry_end.minute) - (r.entry_start.hour * 60 + r.entry_start.minute)

    flags: list[SpecFlag] = []

    def flag(code: str, severity: Severity, message: str) -> None:
        flags.append(SpecFlag(code=code, severity=severity, message=message))

    if r.stop_loss_pct is None and r.trailing_sl_pct is None:
        flag(
            "no_stop_loss",
            "high",
            "No stop loss or trailing stop: a losing option trade is held until a signal or square-off.",
        )
    if r.target_pct is None and not has_signal_exit and r.trailing_sl_pct is None:
        flag(
            "no_profit_exit", "medium", "No target, signal exit or trailing stop: profits are only taken at square-off."
        )
    if r.stop_loss_pct is not None and r.stop_loss_pct > HIGH_STOP_LOSS_PCT:
        flag("wide_stop_loss", "medium", f"Stop loss is {r.stop_loss_pct:g}% of the premium, which is very wide.")
    if rr is not None and rr < MIN_REWARD_TO_RISK:
        flag(
            "low_reward_to_risk",
            "medium",
            f"Target/stop-loss ratio is {rr}: the win rate must exceed 50% to break even.",
        )
    if unused:
        flag("unused_indicator", "low", f"Indicators declared but never used by any rule: {', '.join(unused)}.")
    for rule in rules:
        left = rule.left
        if not (isinstance(left, IndicatorRef) and by_id[left.indicator].type == "rsi"):
            continue
        right = rule.right
        values = (
            list(right.range) if isinstance(right, RangeRef) else [right.value] if isinstance(right, ValueRef) else []
        )
        if any(v < 0 or v > 100 for v in values):
            flag(
                "rsi_out_of_range",
                "high",
                "An RSI rule compares against a value outside 0-100, so it can never trigger as intended.",
            )
            break
    if window < 30:
        flag("short_entry_window", "low", f"Entries are allowed for only {window} minutes a day.")

    sides: list[Literal["bullish", "bearish"]] = []
    if spec.entry_bullish is not None:
        sides.append("bullish")
    if spec.entry_bearish is not None:
        sides.append("bearish")
    return SpecFacts(
        sides=sides,
        indicators=[f"{i.id}:{i.type}" for i in spec.indicators],
        unused_indicators=unused,
        has_stop_loss=r.stop_loss_pct is not None,
        has_target=r.target_pct is not None,
        has_trailing_sl=r.trailing_sl_pct is not None,
        has_signal_exit=has_signal_exit,
        reward_to_risk=rr,
        entry_window_minutes=window,
        flags=flags,
    )
