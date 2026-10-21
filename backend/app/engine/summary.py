"""Deterministic facts about a backtest run, computed in code and handed to the Risk Review agent.

The agent explains and prioritises these; it never computes numbers itself.
"""

from collections import Counter
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel

from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategySpec

# Flag thresholds (documented in README)
MIN_TRADES_WARN, MIN_TRADES_HIGH = 30, 10
DRAWDOWN_WARN_PCT, DRAWDOWN_HIGH_PCT = 20.0, 30.0
CONCENTRATION_WARN_PCT, CONCENTRATION_HIGH_PCT = 40.0, 60.0
MIN_DAYS_WARN = 5
STRESS_EXTRA_SLIPPAGE_POINTS = 1.0
STRESS_EXTRA_SLIPPAGE_PCT = 0.5


Severity = Literal["low", "medium", "high"]


class Flag(BaseModel):
    code: Literal[
        "too_few_trades", "short_period", "high_drawdown", "profit_concentration", "cost_sensitive", "net_loss"
    ]
    severity: Severity
    message: str


class TypeStats(BaseModel):
    trades: int
    net_pnl: float
    win_rate_pct: float


class StressTest(BaseModel):
    description: str
    net_pnl: float
    change_vs_base_pct: float | None


class RiskFacts(BaseModel):
    num_trades: int
    trading_days: int
    trades_per_day: float
    exit_reasons: dict[str, int]
    by_option_type: dict[str, TypeStats]
    avg_holding_minutes: float | None
    longest_losing_streak: int
    best_trade_share_of_gross_profit_pct: float | None
    best_day_share_of_gross_profit_pct: float | None
    gross_pnl: float
    total_costs: float
    costs_pct_of_gross_pnl: float | None
    stress: StressTest | None
    flags: list[Flag]


def stress_spec(spec: StrategySpec) -> tuple[StrategySpec, str]:
    """Copy of the spec with extra slippage, to test how sensitive results are to execution costs."""
    s = spec.model_copy(deep=True)
    if s.costs.slippage.mode == "points":
        s.costs.slippage.value += STRESS_EXTRA_SLIPPAGE_POINTS
        return s, f"+{STRESS_EXTRA_SLIPPAGE_POINTS} point slippage per fill"
    s.costs.slippage.value += STRESS_EXTRA_SLIPPAGE_PCT
    return s, f"+{STRESS_EXTRA_SLIPPAGE_PCT}% slippage per fill"


def build_facts(
    result: BacktestResult, stress_result: BacktestResult | None = None, stress_desc: str = ""
) -> RiskFacts:
    trades = sorted(result.trades, key=lambda t: t.exit_time)
    m = result.metrics
    days = len(m.daily_pnl)
    n = len(trades)

    by_type: dict[str, TypeStats] = {}
    for typ in ("CE", "PE"):
        ts = [t for t in trades if t.option_type == typ]
        if ts:
            wins = sum(t.net_pnl > 0 for t in ts)
            by_type[typ] = TypeStats(
                trades=len(ts),
                net_pnl=round(sum(t.net_pnl for t in ts), 2),
                win_rate_pct=round(wins / len(ts) * 100, 1),
            )

    streak = longest = 0
    for t in trades:
        streak = streak + 1 if t.net_pnl < 0 else 0
        longest = max(longest, streak)

    wins_total = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    best_trade_share = round(max(t.net_pnl for t in trades) / wins_total * 100, 1) if wins_total > 0 else None
    day_wins = [d.pnl for d in m.daily_pnl if d.pnl > 0]
    best_day_share = round(max(day_wins) / sum(day_wins) * 100, 1) if day_wins else None
    hold = [(t.exit_time - t.entry_time) / timedelta(minutes=1) for t in trades]
    gross = round(sum(t.gross_pnl for t in trades), 2)

    stress = None
    if stress_result is not None:
        base = m.total_pnl
        change = round((stress_result.metrics.total_pnl - base) / abs(base) * 100, 1) if base else None
        stress = StressTest(description=stress_desc, net_pnl=stress_result.metrics.total_pnl, change_vs_base_pct=change)

    flags: list[Flag] = []
    sev: Severity
    if n < MIN_TRADES_WARN:
        sev = "high" if n < MIN_TRADES_HIGH else "medium"
        msg = f"Only {n} trades; results are statistically weak (<{MIN_TRADES_WARN})."
        flags.append(Flag(code="too_few_trades", severity=sev, message=msg))
    if days < MIN_DAYS_WARN:
        flags.append(
            Flag(code="short_period", severity="medium", message=f"Only {days} trading days tested (<{MIN_DAYS_WARN}).")
        )
    if m.max_drawdown_pct >= DRAWDOWN_WARN_PCT:
        sev = "high" if m.max_drawdown_pct >= DRAWDOWN_HIGH_PCT else "medium"
        flags.append(
            Flag(code="high_drawdown", severity=sev, message=f"Max drawdown {m.max_drawdown_pct:.1f}% of peak equity.")
        )
    top = max([x for x in (best_trade_share, best_day_share) if x is not None], default=0.0)
    if top >= CONCENTRATION_WARN_PCT:
        sev = "high" if top >= CONCENTRATION_HIGH_PCT else "medium"
        msg = f"{top:.0f}% of gross profit comes from a single best trade or day."
        flags.append(Flag(code="profit_concentration", severity=sev, message=msg))
    if stress is not None and m.total_pnl > 0:
        if stress.net_pnl <= 0:
            flags.append(
                Flag(code="cost_sensitive", severity="high", message=f"Profit disappears with {stress.description}.")
            )
        elif stress.change_vs_base_pct is not None and stress.change_vs_base_pct <= -50:
            msg = f"Profit falls {abs(stress.change_vs_base_pct):.0f}% with {stress.description}."
            flags.append(Flag(code="cost_sensitive", severity="medium", message=msg))
    if m.total_pnl < 0:
        flags.append(Flag(code="net_loss", severity="medium", message=f"Net P&L is negative ({m.total_pnl})."))

    return RiskFacts(
        num_trades=n,
        trading_days=days,
        trades_per_day=round(n / days, 2) if days else 0.0,
        exit_reasons=dict(Counter(t.exit_reason for t in trades)),
        by_option_type=by_type,
        avg_holding_minutes=round(sum(hold) / n, 1) if n else None,
        longest_losing_streak=longest,
        best_trade_share_of_gross_profit_pct=best_trade_share,
        best_day_share_of_gross_profit_pct=best_day_share,
        gross_pnl=gross,
        total_costs=m.total_costs,
        costs_pct_of_gross_pnl=round(m.total_costs / abs(gross) * 100, 1) if gross else None,
        stress=stress,
        flags=flags,
    )
