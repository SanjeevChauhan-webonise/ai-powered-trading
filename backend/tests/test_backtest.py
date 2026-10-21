import pandas as pd
import pytest

from app.engine.backtest import pick_expiry, run_backtest
from app.schemas.backtest import BacktestResult
from tests.engine_helpers import CLOSES, make_options, make_spec, make_underlying

N = len(CLOSES)
ENTRY = 3  # signal at index 2 -> fill at open of index 3


def run(spec=None, options=None, closes=None, lot_size=75, **kw) -> BacktestResult:  # type: ignore[no-untyped-def]
    closes = closes or CLOSES
    return run_backtest(
        spec or make_spec(),
        make_underlying(closes),
        options if options is not None else make_options(len(closes)),
        lot_size=lot_size,
        **kw,
    )


def ts(i: int) -> pd.Timestamp:
    return pd.Timestamp("2024-01-01 09:15") + pd.Timedelta(minutes=i)


def test_entry_at_next_candle_open_no_lookahead() -> None:
    ce = {ENTRY: (105.0, 105.0, 105.0, 105.0)}
    res = run(options=make_options(N, ce=ce), spec=make_spec(risk={"stop_loss_pct": None, "target_pct": None}))
    t = res.trades[0]
    assert t.signal_time == ts(2) and t.entry_time == ts(ENTRY)
    assert t.entry_price == 105.0 and t.option_type == "CE"
    # signal candle's own price (index 2) must not be used
    assert res.trades[0].exit_reason == "square_off" or res.trades[0].exit_reason == "end_of_data"


def test_future_changes_do_not_alter_past_trades() -> None:
    spec = make_spec()
    base_opts = make_options(N, ce={4: (100.0, 100.0, 79.0, 85.0)})  # SL hits at index 4
    a = run(spec, base_opts)
    changed = base_opts.copy()
    changed.loc[changed["timestamp"] > ts(6), ["open", "high", "low", "close"]] = 500.0
    under = list(CLOSES)
    under[10:] = [50.0] * (N - 10)  # crash after the trade is long finished
    b = run(spec, changed, closes=under)
    assert a.trades[0] == b.trades[0]


def test_stop_loss_target_and_tiebreak() -> None:
    sl = run(options=make_options(N, ce={4: (100, 100, 79, 85)})).trades[0]
    assert (sl.exit_reason, sl.exit_price, sl.exit_time) == ("stop_loss", 80.0, ts(4))
    assert sl.gross_pnl == (80 - 100) * 75
    tgt = run(options=make_options(N, ce={4: (100, 141, 99, 120)})).trades[0]
    assert (tgt.exit_reason, tgt.exit_price) == ("target", 140.0)
    both = run(options=make_options(N, ce={4: (100, 150, 70, 100)})).trades[0]
    assert both.exit_reason == "stop_loss" and both.exit_price == 80.0  # stop wins


def test_gap_through_stop_fills_at_open() -> None:
    t = run(options=make_options(N, ce={4: (70, 72, 65, 68)})).trades[0]
    assert t.exit_reason == "stop_loss" and t.exit_price == 70.0


def test_stop_checked_on_entry_candle() -> None:
    t = run(options=make_options(N, ce={ENTRY: (100, 100, 70, 90)})).trades[0]
    assert t.exit_time == ts(ENTRY) and t.exit_reason == "stop_loss" and t.exit_price == 80.0


def test_trailing_stop() -> None:
    spec = make_spec(risk={"stop_loss_pct": None, "target_pct": None, "trailing_sl_pct": 10})
    ce = {4: (100, 121, 100, 120), 5: (118, 118, 107, 110)}  # best close 120 -> stop 108
    t = run(spec, make_options(N, ce=ce)).trades[0]
    assert t.exit_reason == "trailing_sl" and t.exit_price == pytest.approx(108.0) and t.exit_time == ts(5)


def test_square_off() -> None:
    spec = make_spec(risk={"stop_loss_pct": None, "target_pct": None, "square_off": "09:22", "entry_end": "09:20"})
    ce = {7: (130.0, 130.0, 130.0, 130.0)}  # 09:22 is index 7
    t = run(spec, make_options(N, ce=ce)).trades[0]
    assert t.exit_reason == "square_off" and t.exit_time == ts(7) and t.exit_price == 130.0


def test_end_of_data_close() -> None:
    spec = make_spec(risk={"stop_loss_pct": None, "target_pct": None})
    ce = {N - 1: (100, 100, 100, 111.0)}
    t = run(spec, make_options(N, ce=ce)).trades[0]
    assert t.exit_reason == "end_of_data" and t.exit_price == 111.0 and t.exit_time == ts(N - 1)


def test_sell_side_flips_instrument_and_pnl() -> None:
    spec = make_spec(direction="sell")
    pe = {4: (100, 121, 100, 118)}
    t = run(spec, make_options(N, pe=pe)).trades[0]
    assert t.side == "sell" and t.option_type == "PE"  # bullish signal -> short PE
    assert t.exit_reason == "stop_loss" and t.exit_price == 120.0
    assert t.gross_pnl == (100 - 120) * 75
    tgt = run(spec, make_options(N, pe={4: (100, 101, 59, 70)})).trades[0]
    assert tgt.exit_reason == "target" and tgt.exit_price == 60.0 and tgt.gross_pnl == 40 * 75


def test_bearish_signal_buys_pe() -> None:
    closes = [101.0, 101.0, 99.0] + [99.0] * 12
    t = run(closes=closes).trades[0]
    assert t.option_type == "PE" and t.entry_time == ts(3)


def test_option_types_filter() -> None:
    spec = make_spec(instrument={"option_types": ["PE"]})
    assert run(spec).trades == []


def test_costs() -> None:
    spec = make_spec(
        costs={"brokerage_per_order": 20, "tax_pct": 0.1, "slippage": {"mode": "points", "value": 1}},
        risk={"stop_loss_pct": None, "target_pct": 40},
    )
    t = run(spec, make_options(N, ce={4: (100, 150, 100, 130)})).trades[0]
    assert t.entry_price == 101.0 and t.exit_price == pytest.approx(140.4)  # slippage hurts both fills
    assert t.gross_pnl == pytest.approx((140.4 - 101) * 75, abs=0.01)
    assert t.brokerage == 40
    assert t.taxes == pytest.approx(0.1 / 100 * (101 + 140.4) * 75, abs=0.01)
    assert t.net_pnl == pytest.approx(t.gross_pnl - t.brokerage - t.taxes, abs=0.02)
    assert t.slippage_cost == 2 * 75


def test_pct_slippage() -> None:
    spec = make_spec(costs={"brokerage_per_order": 0, "tax_pct": 0, "slippage": {"mode": "pct", "value": 2}})
    assert run(spec).trades[0].entry_price == 102.0


def test_lots_quantity() -> None:
    assert run(make_spec(lots=2), lot_size=75).trades[0].qty == 150


def test_max_trades_per_day_and_reentry() -> None:
    closes = [99.0, 99.0, 101.0, 101.0, 99.0, 99.0, 101.0, 101.0, 101.0, 101.0]
    opts = lambda: make_options(len(closes), ce={4: (100, 100, 79, 85), 7: (100, 100, 79, 85)})  # noqa: E731
    assert len(run(make_spec(), opts(), closes=closes).trades) == 2
    spec = make_spec(risk={"max_trades_per_day": 1})
    assert len(run(spec, opts(), closes=closes).trades) == 1


def test_entry_window() -> None:
    spec = make_spec(risk={"entry_start": "09:30"})
    assert run(spec).trades == []  # fill candle is 09:18


def test_date_range_filters_trading() -> None:
    from datetime import date

    assert run(start=date(2024, 1, 2)).trades == []
    assert len(run(start=date(2024, 1, 1), end=date(2024, 1, 1)).trades) == 1


def test_missing_option_candle_at_entry_is_skipped_and_logged() -> None:
    res = run(options=make_options(N, missing={"CE": {ENTRY}}))
    assert res.trades == []
    assert res.events and res.events[0].kind == "missing_option_candle"


def test_missing_candle_while_in_position_is_skipped() -> None:
    res = run(options=make_options(N, ce={5: (100, 100, 79, 85)}, missing={"CE": {4}}))
    assert res.trades[0].exit_time == ts(5)
    assert any(e.kind == "missing_option_candle" for e in res.events)


def test_signal_exit_fills_next_open() -> None:
    closes = [99.0, 99.0, 101.0, 101.0, 99.0, 99.0, 99.0, 99.0]  # bearish cross at index 4
    spec = make_spec(exit_on_opposite_signal=True, risk={"stop_loss_pct": None, "target_pct": None})
    ce = {5: (123.0, 123.0, 123.0, 123.0)}
    trades = run(spec, make_options(len(closes), ce=ce), closes=closes).trades
    first = trades[0]
    assert first.exit_reason == "signal" and first.exit_time == ts(5) and first.exit_price == 123.0
    assert trades[1].option_type == "PE" and trades[1].entry_time == ts(5)  # reversal on same open


def test_exit_condition_rule() -> None:
    closes = [99.0, 99.0, 101.0, 101.0, 101.0, 90.0, 90.0, 90.0]
    spec = make_spec(
        exit_condition={"left": {"price": "close"}, "op": "<", "right": {"value": 95}},
        risk={"stop_loss_pct": None, "target_pct": None},
        entry_bearish=None,
    )
    t = run(spec, make_options(len(closes)), closes=closes).trades[0]
    assert t.exit_reason == "signal" and t.exit_time == ts(6)


def test_strike_selection() -> None:
    strikes = {90.0: (130.0, 80.0), 100.0: (100.0, 100.0), 110.0: (60.0, 140.0)}
    opts = make_options(N, strikes=strikes)
    spec = make_spec(risk={"stop_loss_pct": None, "target_pct": None})

    def strike_of(**instr):  # type: ignore[no-untyped-def]
        return (
            run(make_spec(instrument={"strike": instr}, risk={"stop_loss_pct": None, "target_pct": None}), opts)
            .trades[0]
            .strike
        )

    assert strike_of(mode="atm") == 100.0
    assert strike_of(mode="offset", offset=1) == 110.0
    assert strike_of(mode="offset", offset=-1) == 90.0
    assert strike_of(mode="nearest_premium", premium=65.0) == 110.0
    assert spec.instrument.strike.mode == "atm"
    res = run(make_spec(instrument={"strike": {"mode": "offset", "offset": 5}}), opts)
    assert res.trades == [] and res.events[0].kind == "no_contract"


def test_pick_expiry() -> None:
    e = [pd.Timestamp(x) for x in ("2024-01-04", "2024-01-11", "2024-01-25", "2024-02-01", "2024-02-29")]
    assert pick_expiry(e, pd.Timestamp("2024-01-04"), "nearest_weekly") == e[0]
    assert pick_expiry(e, pd.Timestamp("2024-01-05"), "nearest_weekly") == e[1]
    assert pick_expiry(e, pd.Timestamp("2024-01-05"), "monthly") == e[2]
    assert pick_expiry(e, pd.Timestamp("2024-01-26"), "monthly") == e[4]
    assert pick_expiry(e, pd.Timestamp("2024-03-01"), "monthly") is None


def test_metrics_consistent_with_trades() -> None:
    res = run(options=make_options(N, ce={4: (100, 141, 99, 120)}))
    assert res.metrics.total_pnl == pytest.approx(sum(t.net_pnl for t in res.trades))
    assert res.equity_curve[-1].equity == pytest.approx(100_000 + res.metrics.total_pnl)
