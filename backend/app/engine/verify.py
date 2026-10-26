"""Independent re-computation of every backtest trade, so the reported P&L can be checked line by line.

Nothing here reuses the engine's loop: each figure is rebuilt from the audit data stored on the trade (raw prices,
candles, stop/target levels, lots, costs) and compared with what the engine reported.
"""

from app.schemas.backtest import BacktestMetrics, BacktestTrade, CheckLine, Verification
from app.schemas.strategy import StrategySpec

TOL = 0.011  # prices are rounded to 2 decimals
TOL_MONEY = 0.06  # P&L is rounded once at the end; qty multiplies the rounding of the prices


def _line(name: str, reported: float | None, recomputed: float | None, tol: float = TOL, note: str = "") -> CheckLine:
    ok = reported is not None and recomputed is not None and abs(reported - recomputed) <= tol
    return CheckLine(name=name, reported=reported, recomputed=recomputed, ok=ok, note=note)


def _slip(raw: float, spec: StrategySpec) -> float:
    s = spec.costs.slippage
    return s.value if s.mode == "points" else raw * s.value / 100


def check_trade(t: BacktestTrade, spec: StrategySpec) -> list[CheckLine]:
    buy = t.side == "buy"
    sign = 1 if buy else -1
    lines: list[CheckLine] = []
    if t.entry_raw is None or t.exit_raw is None or not t.candles:
        return [
            CheckLine(name="Audit data", ok=False, note="this trade was stored without audit data; re-run the backtest")
        ]

    lines.append(_line("Quantity", t.qty, (t.lots or 0) * (t.lot_size or 0), 0, f"{t.lots} lot × {t.lot_size}"))
    first = t.candles[0]
    lines.append(
        _line(
            "Entry candle open",
            t.entry_raw,
            first.open,
            1e-9,
            f"candle {first.timestamp:%H:%M} (the candle after the signal)",
        )
    )
    entry_fill = max(0.0, t.entry_raw + sign * _slip(t.entry_raw, spec))
    exit_fill = max(0.0, t.exit_raw - sign * _slip(t.exit_raw, spec))
    lines.append(_line("Entry fill", t.entry_price, entry_fill, TOL, "open + slippage against you"))

    last = next((c for c in t.candles if c.timestamp == t.exit_time), None)
    expect: float | None = None
    note = t.exit_reason
    if last is None:
        lines.append(CheckLine(name="Exit candle", ok=False, note="no candle at the exit time"))
    elif t.exit_reason in ("stop_loss", "trailing_sl"):
        level = t.stop_price if t.exit_reason == "stop_loss" else t.trail_stop_price
        if level is not None:
            expect = min(last.open, level) if buy else max(last.open, level)
            hit = (last.low <= level) if buy else (last.high >= level)
            note = f"stop {level:.2f}; candle low {last.low}, high {last.high}" + ("" if hit else " (stop NOT reached)")
            if not hit and not ((last.open <= level) if buy else (last.open >= level)):
                expect = None
    elif t.exit_reason == "target":
        if t.target_price is not None:
            expect = max(last.open, t.target_price) if buy else min(last.open, t.target_price)
            note = f"target {t.target_price:.2f}; candle high {last.high}, low {last.low}"
    elif t.exit_reason in ("signal", "square_off"):
        expect = last.open
        note = f"{t.exit_reason}: exits at the open of the {last.timestamp:%H:%M} candle"
    else:  # end_of_data: closes at the last close seen
        expect = t.candles[-1].close
        note = "end of data: closes at the last available close"
    lines.append(_line("Exit price rule", t.exit_raw, expect, TOL, note))
    lines.append(_line("Exit fill", t.exit_price, exit_fill, TOL, "exit price - slippage against you"))

    gross = (exit_fill - entry_fill) * t.qty * sign
    lines.append(_line("Gross P&L", t.gross_pnl, gross, TOL_MONEY, "(exit fill - entry fill) × qty"))
    brokerage = 2 * spec.costs.brokerage_per_order
    lines.append(_line("Brokerage", t.brokerage, brokerage, TOL, "2 orders"))
    taxes = spec.costs.tax_pct / 100 * (entry_fill + exit_fill) * t.qty
    lines.append(_line("Taxes", t.taxes, taxes, TOL_MONEY, f"{spec.costs.tax_pct}% of turnover"))
    lines.append(_line("Net P&L", t.net_pnl, gross - brokerage - taxes, TOL_MONEY, "gross - brokerage - taxes"))
    return lines


def verify_result(trades: list[BacktestTrade], spec: StrategySpec, metrics: BacktestMetrics) -> Verification:
    """Fill each trade's `checks` / `verified` and summarise. Also checks the trades add up to the reported total."""
    failed: list[int] = []
    for t in trades:
        t.checks = check_trade(t, spec)
        t.verified = all(c.ok for c in t.checks)
        if not t.verified:
            failed.append(t.id)
    total = round(sum(t.net_pnl for t in trades), 2)
    return Verification(
        checked=len(trades), passed=len(trades) - len(failed), failed=len(failed), sum_of_trades=total,
        reported_total_pnl=metrics.total_pnl, totals_match=abs(total - metrics.total_pnl) <= TOL_MONEY,
        failed_trade_ids=failed[:200],
    )  # fmt: skip
