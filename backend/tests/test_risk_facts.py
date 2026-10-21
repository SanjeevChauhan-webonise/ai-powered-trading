from app.engine.metrics import compute_metrics, equity_curve
from app.engine.summary import build_facts, stress_spec
from app.schemas.backtest import BacktestResult
from tests.engine_helpers import make_spec
from tests.test_metrics import DAYS, trade


def result(pnls: list[tuple[int, float]], capital: float = 1000.0) -> BacktestResult:
    trades = [trade(i + 1, day, pnl) for i, (day, pnl) in enumerate(pnls)]
    return BacktestResult(
        strategy_name="t", start=None, end=None, capital=capital, lot_size=1, trades=trades,
        equity_curve=equity_curve(trades, capital), metrics=compute_metrics(trades, capital, DAYS), events=[],
    )  # fmt: skip


def test_facts_hand_computed() -> None:
    r = result([(1, 100), (1, -50), (2, -200), (4, 300)])
    f = build_facts(r)
    assert f.num_trades == 4 and f.trading_days == 4 and f.trades_per_day == 1.0
    assert f.exit_reasons == {"target": 4}
    assert f.by_option_type["CE"].trades == 4 and f.by_option_type["CE"].net_pnl == 150
    assert f.by_option_type["CE"].win_rate_pct == 50.0 and "PE" not in f.by_option_type
    assert f.longest_losing_streak == 2
    assert f.best_trade_share_of_gross_profit_pct == 75.0  # 300 / (100 + 300)
    assert f.best_day_share_of_gross_profit_pct == 85.7  # day 4: 300, day 1: 50 -> 300 / 350
    assert f.avg_holding_minutes == 0.0 and f.gross_pnl == 150
    codes = {x.code: x.severity for x in f.flags}
    assert codes["too_few_trades"] == "high" and codes["profit_concentration"] == "high"
    assert codes["high_drawdown"] == "medium"  # equity 1100 -> 850 is a 22.7% drawdown
    assert "short_period" in codes and "net_loss" not in codes


def test_cost_stress_flags() -> None:
    base = result([(1, 100), (2, 100), (3, 100)] * 4)
    dead = result([(1, -10)])  # profit disappears under stress
    f = build_facts(base, dead, "+1 point")
    assert f.stress and f.stress.net_pnl == -10 and f.stress.change_vs_base_pct == -100.8  # (-10 - 1200) / 1200
    assert {x.code: x.severity for x in f.flags}["cost_sensitive"] == "high"
    halved = result([(1, 40)] * 5)  # 200 vs base 1200 -> -83%
    assert {x.code: x.severity for x in build_facts(base, halved, "x").flags}["cost_sensitive"] == "medium"
    mild = result([(1, 90)] * 12)  # 1080 vs 1200 -> -10%
    assert "cost_sensitive" not in {x.code for x in build_facts(base, mild, "x").flags}


def test_drawdown_and_loss_flags() -> None:
    f = build_facts(result([(1, -250), (2, -100)] * 20, capital=1000.0))
    codes = {x.code: x.severity for x in f.flags}
    assert codes["high_drawdown"] == "high" and codes["net_loss"] == "medium"
    assert "too_few_trades" not in codes
    assert f.best_trade_share_of_gross_profit_pct is None  # no winning trades


def test_no_trades() -> None:
    f = build_facts(result([]))
    assert f.num_trades == 0 and f.avg_holding_minutes is None and f.longest_losing_streak == 0
    assert f.costs_pct_of_gross_pnl is None


def test_stress_spec_does_not_mutate_original() -> None:
    spec = make_spec()
    s, desc = stress_spec(spec)
    assert s.costs.slippage.value == spec.costs.slippage.value + 1.0 and "point" in desc
    assert spec.costs.slippage.value == 0.0
    pct = make_spec(costs={"slippage": {"mode": "pct", "value": 1.0}})
    s2, desc2 = stress_spec(pct)
    assert s2.costs.slippage.value == 1.5 and "%" in desc2
