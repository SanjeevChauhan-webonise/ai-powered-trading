from app.engine.verify import check_trade, verify_result
from tests.engine_helpers import make_options, make_spec
from tests.test_backtest import ENTRY, N, run


def _spec_with_slippage():  # type: ignore[no-untyped-def]
    return make_spec(costs={"slippage": {"mode": "points", "value": 0.5}, "brokerage_per_order": 20, "tax_pct": 0.05})


def test_every_trade_reconciles_with_an_independent_recomputation() -> None:
    ce = {ENTRY + 2: (100.0, 150.0, 99.0, 140.0)}  # hits the 40% target in the third candle
    res = run(spec=_spec_with_slippage(), options=make_options(N, ce=ce))
    assert res.trades and res.verification is not None
    v = res.verification
    assert v.failed == 0 and v.passed == v.checked == len(res.trades) and v.totals_match
    t = res.trades[0]
    assert t.verified is True and t.lots == 1 and t.lot_size == 75 and t.candles
    assert t.candles[0].timestamp == t.entry_time and t.candles[-1].timestamp == t.exit_time
    assert {c.name for c in t.checks} >= {"Quantity", "Entry fill", "Exit price rule", "Gross P&L", "Net P&L"}


def test_a_tampered_trade_is_flagged() -> None:
    res = run(spec=_spec_with_slippage())
    t = res.trades[0]
    t.net_pnl += 500  # someone edits the result
    lines = check_trade(t, _spec_with_slippage())
    bad = {c.name for c in lines if not c.ok}
    assert "Net P&L" in bad
    assert verify_result(res.trades, _spec_with_slippage(), res.metrics).totals_match is False


def test_trade_without_audit_data_is_not_silently_passed() -> None:
    res = run()
    t = res.trades[0]
    t.candles = []
    assert [c.ok for c in check_trade(t, make_spec())] == [False]
