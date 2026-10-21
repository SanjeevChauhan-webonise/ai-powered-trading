from collections.abc import Sequence
from datetime import date

import numpy as np

from app.schemas.backtest import BacktestMetrics, BacktestTrade, DailyPnl, EquityPoint

TRADING_DAYS_PER_YEAR = 252


def equity_curve(trades: Sequence[BacktestTrade], capital: float) -> list[EquityPoint]:
    """Realised equity after each trade close, in exit order."""
    curve: list[EquityPoint] = []
    equity = capital
    for t in sorted(trades, key=lambda t: t.exit_time):
        equity += t.net_pnl
        curve.append(EquityPoint(timestamp=t.exit_time, equity=round(equity, 2)))
    return curve


def compute_metrics(trades: Sequence[BacktestTrade], capital: float, trading_days: Sequence[date]) -> BacktestMetrics:
    """Sharpe: daily net P&L / capital over all trading days (zero-P&L days included), rf=0, sqrt(252)."""
    pnl = np.array([t.net_pnl for t in sorted(trades, key=lambda t: t.exit_time)], dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]

    equity = np.concatenate([[capital], capital + np.cumsum(pnl)])
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    dd_pct = np.where(peak > 0, dd / peak * 100, 0.0)

    by_day: dict[date, list[float]] = {}
    for t in trades:
        by_day.setdefault(t.exit_time.date(), []).append(t.net_pnl)
    days = sorted(set(trading_days) | set(by_day))
    daily = [DailyPnl(date=d, pnl=round(sum(by_day.get(d, [])), 2), trades=len(by_day.get(d, []))) for d in days]
    rets = np.array([d.pnl for d in daily]) / capital
    sharpe = None
    if len(rets) >= 2 and rets.std(ddof=1) > 0:
        sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))

    n = len(pnl)
    return BacktestMetrics(
        total_pnl=round(float(pnl.sum()), 2),
        num_trades=n,
        win_rate_pct=round(len(wins) / n * 100, 2) if n else None,
        avg_win=round(float(wins.mean()), 2) if len(wins) else None,
        avg_loss=round(float(losses.mean()), 2) if len(losses) else None,
        profit_factor=round(float(wins.sum() / -losses.sum()), 4) if len(losses) else None,
        max_drawdown=round(float(dd.max()), 2),
        max_drawdown_pct=round(float(dd_pct.max()), 4),
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        expectancy=round(float(pnl.mean()), 2) if n else None,
        best_trade=round(float(pnl.max()), 2) if n else None,
        worst_trade=round(float(pnl.min()), 2) if n else None,
        total_costs=round(sum(t.brokerage + t.taxes for t in trades), 2),
        daily_pnl=daily,
    )
