"""Deterministic options backtester. Pure: no DB, no LLM, no I/O.

Timing: signals are evaluated on candle close (t); entries and signal exits fill at the OPEN of t+1.
Within a candle, checks run in this order: signal exit, square-off, stop (incl. trailing), target.
If stop and target are both reachable in one candle the stop wins (conservative).
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.data.resample import resample
from app.data.validate import infer_timeframe_minutes
from app.engine.conditions import compute_indicators, evaluate
from app.engine.metrics import compute_metrics, equity_curve
from app.schemas.backtest import BacktestResult, BacktestTrade, EngineEvent, ExitReason
from app.schemas.strategy import Condition, StrategySpec

MAX_EVENTS = 500
Candle = tuple[float, float, float, float]  # open, high, low, close
OptionType = Literal["CE", "PE"]
View = Literal["bull", "bear"]


@dataclass
class _Position:
    view: View
    side: Literal["buy", "sell"]
    option_type: OptionType
    expiry: pd.Timestamp
    strike: float
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_raw: float
    entry_price: float
    qty: int
    candles: dict[pd.Timestamp, Candle]
    stop: float | None
    target: float | None
    trail_pct: float | None
    extreme: float
    trail_stop: float | None
    last_ts: pd.Timestamp
    last_close: float


def pick_expiry(expiries: list[pd.Timestamp], day: pd.Timestamp, mode: str) -> pd.Timestamp | None:
    """nearest_weekly: first expiry >= day. monthly: last available expiry of the month, first one >= day."""
    unique = sorted(set(expiries))
    live = [e for e in unique if e >= day]
    if not live:
        return None
    if mode == "nearest_weekly":
        return live[0]
    month_end: dict[tuple[int, int], pd.Timestamp] = {}
    for e in unique:
        month_end[(e.year, e.month)] = e
    return next((e for e in sorted(month_end.values()) if e >= day), None)


def select_strike(snap: pd.DataFrame, spot: float, mode: str, offset: int, premium: float | None) -> float | None:
    """snap: option candles at one timestamp, already filtered to one expiry and option type."""
    strikes = np.sort(snap["strike"].unique())
    if mode == "nearest_premium":
        assert premium is not None
        return float(snap["strike"].to_numpy()[(snap["open"] - premium).abs().to_numpy().argmin()])
    idx = int(np.abs(strikes - spot).argmin()) + (offset if mode == "offset" else 0)
    return float(strikes[idx]) if 0 <= idx < len(strikes) else None


def _signal(
    cond: Condition | None, frames: dict[str, pd.DataFrame], df: pd.DataFrame, types: dict[str, str]
) -> np.ndarray:
    if cond is None:
        return np.zeros(len(df), dtype=bool)
    return evaluate(cond, frames, df, types).to_numpy(dtype=bool)


class _Runner:
    def __init__(
        self,
        spec: StrategySpec,
        under: pd.DataFrame,
        opts: pd.DataFrame,
        lot_size: int,
        start: date | None,
        end: date | None,
    ) -> None:  # noqa: E501
        self.spec, self.under, self.opts, self.lot_size = spec, under, opts, lot_size
        self.start, self.end = start, end
        self.by_ts = opts.groupby("timestamp").indices
        self.contracts = opts.groupby(["expiry", "strike", "option_type"], sort=False).indices
        self._candle_cache: dict[tuple[pd.Timestamp, float, str], dict[pd.Timestamp, Candle]] = {}
        self.trades: list[BacktestTrade] = []
        self.events: list[EngineEvent] = []
        self.events_truncated = False

    # ---- helpers -------------------------------------------------------------------------------
    def _event(self, ts: pd.Timestamp, kind: str, msg: str) -> None:
        if len(self.events) >= MAX_EVENTS:
            self.events_truncated = True
            return
        self.events.append(EngineEvent(timestamp=ts.to_pydatetime(), kind=kind, message=msg))

    def _candles(self, expiry: pd.Timestamp, strike: float, typ: str) -> dict[pd.Timestamp, Candle]:
        key = (expiry, strike, typ)
        if key not in self._candle_cache:
            sub = self.opts.iloc[self.contracts[key]]
            self._candle_cache[key] = dict(
                zip(
                    sub["timestamp"],
                    sub[["open", "high", "low", "close"]].itertuples(index=False, name=None),
                    strict=True,
                )
            )
        return self._candle_cache[key]

    def _fill(self, raw: float, adverse: int) -> float:
        """adverse=+1 raises the price paid/received, -1 lowers it."""
        sl = self.spec.costs.slippage
        slip = sl.value if sl.mode == "points" else raw * sl.value / 100
        return max(0.0, raw + adverse * slip)

    # ---- entry ---------------------------------------------------------------------------------
    def _try_enter(
        self, view: View, ts: pd.Timestamp, signal_ts: pd.Timestamp, spot: float, trades_today: int
    ) -> _Position | None:  # noqa: E501
        spec, risk = self.spec, self.spec.risk
        buy = spec.direction == "buy"
        typ: OptionType = ("CE" if view == "bull" else "PE") if buy else ("PE" if view == "bull" else "CE")
        if typ not in spec.instrument.option_types:
            return None
        if risk.max_trades_per_day is not None and trades_today >= risk.max_trades_per_day:
            return None
        if not (risk.entry_start <= ts.time() < min(risk.entry_end, risk.square_off)):
            return None
        rows = self.by_ts.get(ts)
        if rows is None:
            self._event(ts, "no_contract", "no option candles at entry time")
            return None
        snap = self.opts.iloc[rows]
        snap = snap[snap["option_type"] == typ]
        if snap.empty:
            self._event(ts, "missing_option_candle", f"no {typ} candles at entry time; skipped")
            return None
        expiry = pick_expiry(list(snap["expiry"]), ts.normalize(), spec.instrument.expiry)
        if expiry is None:
            self._event(ts, "no_contract", f"no {spec.instrument.expiry} expiry available for {typ}")
            return None
        snap = snap[snap["expiry"] == expiry]
        k = spec.instrument.strike
        strike = select_strike(snap, spot, k.mode, k.offset, k.premium)
        if strike is None:
            self._event(ts, "no_contract", f"strike selection '{k.mode}' ({k.offset}) outside available strikes")
            return None
        candles = self._candles(expiry, strike, typ)
        candle = candles.get(ts)
        if candle is None:
            self._event(ts, "missing_option_candle", f"{typ} {strike} {expiry.date()} has no candle at entry; skipped")
            return None
        raw = candle[0]
        fill = self._fill(raw, +1 if buy else -1)
        sign = 1 if buy else -1  # long premium: stop below; short premium: stop above
        stop = fill * (1 - sign * risk.stop_loss_pct / 100) if risk.stop_loss_pct else None
        target = fill * (1 + sign * risk.target_pct / 100) if risk.target_pct else None
        trail = fill * (1 - sign * risk.trailing_sl_pct / 100) if risk.trailing_sl_pct else None
        return _Position(
            view=view, side=spec.direction, option_type=typ, expiry=expiry, strike=strike,
            signal_time=signal_ts, entry_time=ts, entry_raw=raw, entry_price=fill,
            qty=spec.lots * self.lot_size, candles=candles, stop=stop, target=target,
            trail_pct=risk.trailing_sl_pct, extreme=fill, trail_stop=trail, last_ts=ts, last_close=candle[3],
        )  # fmt: skip

    # ---- exit ----------------------------------------------------------------------------------
    def _check_exit(
        self, pos: _Position, ts: pd.Timestamp, candle: Candle, pending_exit: bool, entry_candle: bool
    ) -> tuple[float, ExitReason] | None:  # noqa: E501
        o, h, lo, c = candle
        if pending_exit and not entry_candle:
            return o, "signal"
        if ts.time() >= self.spec.risk.square_off:
            return o, "square_off"
        buy = pos.side == "buy"
        levels = [(v, r) for v, r in ((pos.stop, "stop_loss"), (pos.trail_stop, "trailing_sl")) if v is not None]
        if levels:
            stop, reason = max(levels) if buy else min(levels)
            if buy and (o <= stop or lo <= stop):
                return min(o, stop), reason  # type: ignore[return-value]
            if not buy and (o >= stop or h >= stop):
                return max(o, stop), reason  # type: ignore[return-value]
        if pos.target is not None:
            if buy and (o >= pos.target or h >= pos.target):
                return max(o, pos.target), "target"
            if not buy and (o <= pos.target or lo <= pos.target):
                return min(o, pos.target), "target"
        # survived the candle: ratchet trailing stop on the close
        pos.last_ts, pos.last_close = ts, c
        if pos.trail_pct:
            if buy:
                pos.extreme = max(pos.extreme, c)
                pos.trail_stop = pos.extreme * (1 - pos.trail_pct / 100)
            else:
                pos.extreme = min(pos.extreme, c)
                pos.trail_stop = pos.extreme * (1 + pos.trail_pct / 100)
        return None

    def _close(self, pos: _Position, ts: pd.Timestamp, raw_exit: float, reason: ExitReason) -> None:
        buy = pos.side == "buy"
        exit_fill = self._fill(raw_exit, -1 if buy else +1)
        gross = (exit_fill - pos.entry_price) * pos.qty * (1 if buy else -1)
        slip = (abs(pos.entry_price - pos.entry_raw) + abs(exit_fill - raw_exit)) * pos.qty
        costs = self.spec.costs
        brokerage = 2 * costs.brokerage_per_order
        taxes = costs.tax_pct / 100 * (pos.entry_price + exit_fill) * pos.qty
        self.trades.append(
            BacktestTrade(
                id=len(self.trades) + 1, side=pos.side, option_type=pos.option_type,
                expiry=pos.expiry.date(), strike=pos.strike,
                signal_time=pos.signal_time.to_pydatetime(), entry_time=pos.entry_time.to_pydatetime(),
                exit_time=ts.to_pydatetime(),
                entry_price=round(pos.entry_price, 2), exit_price=round(exit_fill, 2), qty=pos.qty,
                gross_pnl=round(gross, 2), slippage_cost=round(slip, 2),
                brokerage=round(brokerage, 2), taxes=round(taxes, 2),
                net_pnl=round(gross - brokerage - taxes, 2), exit_reason=reason,
            )
        )  # fmt: skip

    # ---- main loop -----------------------------------------------------------------------------
    def run(self, bull: np.ndarray, bear: np.ndarray, exit_sig: np.ndarray) -> None:
        spec = self.spec
        times = list(self.under["timestamp"])
        opens = self.under["open"].to_numpy()
        pos: _Position | None = None
        pending_entry: View | None = None
        pending_signal_ts = times[0]
        pending_exit = False
        cur_day: date | None = None
        trades_today = 0

        for i, ts in enumerate(times):
            day = ts.date()
            if day != cur_day:
                if pos is not None:
                    self._close(pos, pos.last_ts, pos.last_close, "end_of_data")
                    pos = None
                cur_day, trades_today = day, 0
                pending_entry, pending_exit = None, False
            in_range = (self.start is None or day >= self.start) and (self.end is None or day <= self.end)

            if pos is not None:
                candle = pos.candles.get(ts)
                if candle is None:
                    self._event(ts, "missing_option_candle", f"{pos.option_type} {pos.strike} has no candle; skipped")
                else:
                    res = self._check_exit(pos, ts, candle, pending_exit, entry_candle=False)
                    if res:
                        self._close(pos, ts, *res)
                        pos = None
                    pending_exit = False

            if pos is None and pending_entry is not None and in_range:
                new = self._try_enter(pending_entry, ts, pending_signal_ts, float(opens[i]), trades_today)
                if new is not None:
                    trades_today += 1
                    candle = new.candles[ts]
                    res = self._check_exit(new, ts, candle, False, entry_candle=True)
                    if res:
                        self._close(new, ts, *res)
                    else:
                        pos = new
            pending_entry = None

            if in_range:
                b, s = bool(bull[i]), bool(bear[i])
                if b != s:
                    pending_entry, pending_signal_ts = ("bull" if b else "bear"), ts
                if pos is not None and not pending_exit:
                    opposite = (pos.view == "bull" and s) or (pos.view == "bear" and b)
                    pending_exit = bool(exit_sig[i]) or (spec.exit_on_opposite_signal and opposite)

        if pos is not None:
            self._close(pos, pos.last_ts, pos.last_close, "end_of_data")


def run_backtest(
    spec: StrategySpec,
    underlying: pd.DataFrame,
    options: pd.DataFrame,
    *,
    lot_size: int,
    start: date | None = None,
    end: date | None = None,
    capital: float = 100_000.0,
) -> BacktestResult:
    """Run a strategy on normalized underlying + option candles. Indicators warm up on all data before `start`."""
    if underlying["symbol"].nunique() > 1:
        raise ValueError("underlying candles must contain a single symbol")
    under = underlying.sort_values("timestamp").reset_index(drop=True)
    opts = options.reset_index(drop=True)
    if spec.timeframe_minutes and spec.timeframe_minutes != infer_timeframe_minutes(under["timestamp"]):
        under = resample(under, "underlying", spec.timeframe_minutes)
        opts = resample(opts, "options", spec.timeframe_minutes)

    types: dict[str, str] = {i.id: i.type for i in spec.indicators}
    frames = compute_indicators(spec.indicators, under)
    bull = _signal(spec.entry_bullish, frames, under, types)
    bear = _signal(spec.entry_bearish, frames, under, types)
    exit_sig = _signal(spec.exit_condition, frames, under, types)

    runner = _Runner(spec, under, opts, lot_size, start, end)
    runner.run(bull, bear, exit_sig)

    days = sorted(
        {
            t.date()
            for t in under["timestamp"]
            if (start is None or t.date() >= start) and (end is None or t.date() <= end)
        }
    )  # noqa: E501
    return BacktestResult(
        strategy_name=spec.name, start=start, end=end, capital=capital, lot_size=lot_size,
        trades=runner.trades, equity_curve=equity_curve(runner.trades, capital),
        metrics=compute_metrics(runner.trades, capital, days),
        events=runner.events, events_truncated=runner.events_truncated,
    )  # fmt: skip


__all__ = ["run_backtest", "pick_expiry", "select_strike"]
