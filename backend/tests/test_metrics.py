from datetime import date, datetime

import numpy as np
import pytest

from app.engine.metrics import compute_metrics, equity_curve
from app.schemas.backtest import BacktestTrade


def trade(i: int, day: int, pnl: float) -> BacktestTrade:
    t = datetime(2024, 1, day, 10, i)
    return BacktestTrade(
        id=i, side="buy", option_type="CE", expiry=date(2024, 1, 25), strike=100, signal_time=t, entry_time=t,
        exit_time=t, entry_price=1, exit_price=1, qty=1, gross_pnl=pnl, slippage_cost=0, brokerage=0, taxes=0,
        net_pnl=pnl, exit_reason="target",
    )  # fmt: skip


DAYS = [date(2024, 1, d) for d in (1, 2, 3, 4)]


def test_metrics_hand_computed() -> None:
    trades = [trade(1, 1, 100), trade(2, 1, -50), trade(3, 2, -200), trade(4, 4, 300)]
    m = compute_metrics(trades, 1000.0, DAYS)
    assert m.total_pnl == 150 and m.num_trades == 4
    assert m.win_rate_pct == 50.0
    assert m.avg_win == 200.0 and m.avg_loss == -125.0
    assert m.profit_factor == pytest.approx(400 / 250)
    assert m.expectancy == 37.5
    assert (m.best_trade, m.worst_trade) == (300, -200)
    # equity: 1000,1100,1050,850,1150 -> peak 1100, trough 850
    assert m.max_drawdown == 250
    assert m.max_drawdown_pct == pytest.approx(250 / 1100 * 100, abs=1e-3)
    assert [(d.date.day, d.pnl, d.trades) for d in m.daily_pnl] == [(1, 50, 2), (2, -200, 1), (3, 0, 0), (4, 300, 1)]
    rets = np.array([50, -200, 0, 300]) / 1000
    assert m.sharpe == pytest.approx(rets.mean() / rets.std(ddof=1) * np.sqrt(252), abs=1e-3)


def test_metrics_edge_cases() -> None:
    empty = compute_metrics([], 1000.0, DAYS)
    assert empty.num_trades == 0 and empty.win_rate_pct is None and empty.max_drawdown == 0
    assert empty.sharpe is None
    only_wins = compute_metrics([trade(1, 1, 10), trade(2, 2, 20)], 1000.0, DAYS)
    assert only_wins.profit_factor is None and only_wins.avg_loss is None
    assert only_wins.max_drawdown == 0


def test_equity_curve() -> None:
    curve = equity_curve([trade(2, 2, -50), trade(1, 1, 100)], 1000.0)
    assert [p.equity for p in curve] == [1100, 1050]
