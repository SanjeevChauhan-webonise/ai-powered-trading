"""Paper trading on a replayed dataset: orders fill at the simulated market price, positions are marked to it,
and stop / target / square-off / expiry exits run as the market clock advances.

Rules: only long options (buy to open, sell to close); one account per user; costs are charged when a trade closes
(2 x brokerage per closing trade plus taxes, the same defaults as the backtest engine) so that cash always moves by
exactly the trade's net P&L. Educational simulation: nothing here is sent to a broker.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.models import PaperAccount, PaperOrder, PaperPosition, PaperTrade, PipelineRun
from app.data.models import Dataset
from app.paper.prices import PriceBook

BROKERAGE_PER_ORDER = 20.0
TAX_PCT = 0.05  # % of turnover (entry + exit)
DEFAULT_BALANCE = 500_000.0
DEFAULT_START_DAYS_BACK = 3  # a new clock starts on the first candle of the 3rd-last trading day


class PaperError(ValueError):
    """A problem the user can fix (bad input or a rule of the simulation). Becomes HTTP 400."""


class PaperConflict(PaperError):
    """The request is valid but not possible right now (for example another dataset's positions are open). HTTP 409."""


def _hex() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _t(ts: Any) -> datetime:
    return pd.Timestamp(ts).to_pydatetime()


# ---- account and clock -------------------------------------------------------------------------
def get_account(db: Session, user_id: str) -> PaperAccount:
    acct = db.scalar(select(PaperAccount).where(PaperAccount.user_id == user_id))
    if acct is None:
        acct = PaperAccount(id=_hex(), user_id=user_id, starting_balance=DEFAULT_BALANCE, cash=DEFAULT_BALANCE)
        db.add(acct)
        db.commit()
    return acct


def reset_account(db: Session, acct: PaperAccount, starting_balance: float | None) -> PaperAccount:
    for model in (PaperPosition, PaperOrder, PaperTrade):
        db.execute(delete(model).where(model.account_id == acct.id))
    if starting_balance is not None:
        acct.starting_balance = starting_balance
    acct.cash = acct.starting_balance
    acct.dataset_id, acct.clock_time = None, None
    db.commit()
    return acct


def _dataset(db: Session, dataset_id: str) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise PaperError("Dataset not found")
    if not ds.options_rows or not ds.underlying_rows:
        raise PaperError("The dataset needs both underlying and option candles")
    return ds


def default_clock_start(book: PriceBook, dataset_id: str) -> datetime:
    tl = book.timeline(dataset_id)
    days = list(dict.fromkeys(tl.dt.date))
    day = days[max(0, len(days) - DEFAULT_START_DAYS_BACK)]
    return _t(tl[tl.dt.date == day].iloc[0])


def start_clock(db: Session, book: PriceBook, acct: PaperAccount, dataset_id: str, at: datetime | None) -> PaperAccount:
    _dataset(db, dataset_id)
    open_positions = db.scalar(
        select(func.count()).select_from(PaperPosition).where(PaperPosition.account_id == acct.id)
    )
    if open_positions and acct.dataset_id != dataset_id:
        raise PaperConflict("Close your open positions (or reset the account) before replaying a different dataset")
    if open_positions:
        raise PaperConflict("Close your open positions (or reset the account) before moving the clock back to a start")
    tl = book.timeline(dataset_id)
    if at is None:
        clock = default_clock_start(book, dataset_id)
    else:
        i = int(tl.searchsorted(pd.Timestamp(at), side="left"))
        clock = _t(tl.iloc[min(i, len(tl) - 1)])
    acct.dataset_id, acct.clock_time = dataset_id, clock
    db.commit()
    return acct


def _market(db: Session, acct: PaperAccount) -> tuple[Dataset, datetime]:
    if not acct.dataset_id or acct.clock_time is None:
        raise PaperError("Start the market clock first: choose a dataset to replay")
    return _dataset(db, acct.dataset_id), acct.clock_time


# ---- summary -----------------------------------------------------------------------------------
@dataclass
class Mark:
    position: PaperPosition
    price: float
    unrealized: float


def marks(db: Session, book: PriceBook, acct: PaperAccount) -> list[Mark]:
    positions = list(
        db.scalars(select(PaperPosition).where(PaperPosition.account_id == acct.id).order_by(PaperPosition.opened_at))
    )
    out = []
    for p in positions:
        price = None
        if acct.clock_time is not None and acct.dataset_id == p.dataset_id:
            price = book.price_at(p.dataset_id, p.expiry, p.strike, p.option_type, acct.clock_time)
        price = price if price is not None else p.avg_price
        out.append(Mark(p, price, round((price - p.avg_price) * p.qty, 2)))
    return out


def summary(db: Session, book: PriceBook, acct: PaperAccount) -> dict[str, Any]:
    ms = marks(db, book, acct)
    realized = db.scalar(
        select(func.coalesce(func.sum(PaperTrade.net_pnl), 0.0)).where(PaperTrade.account_id == acct.id)
    )
    market_value = sum(m.price * m.position.qty for m in ms)
    clock_end = _t(book.timeline(acct.dataset_id).iloc[-1]) if acct.dataset_id else None
    return {
        "starting_balance": acct.starting_balance,
        "cash": round(acct.cash, 2),
        "market_value": round(market_value, 2),
        "equity": round(acct.cash + market_value, 2),
        "realized_pnl": round(float(realized or 0.0), 2),
        "unrealized_pnl": round(sum(m.unrealized for m in ms), 2),
        "open_positions": len(ms),
        "dataset_id": acct.dataset_id,
        "clock_time": acct.clock_time,
        "clock_end": clock_end,
    }


# ---- trading -----------------------------------------------------------------------------------
def _record_order(db: Session, acct: PaperAccount, ds: Dataset, clock: datetime, **kw: Any) -> PaperOrder:
    order = PaperOrder(
        id=_hex(), account_id=acct.id, user_id=acct.user_id, dataset_id=ds.id, underlying=ds.underlying,
        placed_at=clock, **kw,
    )  # fmt: skip
    db.add(order)
    return order


def buy(
    db: Session,
    book: PriceBook,
    acct: PaperAccount,
    *,
    expiry: date,
    strike: float,
    option_type: str,
    lots: int,
    stop_pct: float | None = None,
    target_pct: float | None = None,
    square_off: str | None = None,
    run_id: str | None = None,
    source: str = "manual",
) -> PaperOrder:
    ds, clock = _market(db, acct)
    if expiry not in book.listed_expiries(ds.id, clock):
        raise PaperError(f"{expiry} is not an available expiry at the market time ({clock:%d %b %Y %H:%M})")
    price = book.price_at(ds.id, expiry, strike, option_type, clock)
    if price is None or price <= 0:
        raise PaperError("That contract has no price at the market time")
    qty = lots * ds.lot_size
    cost = round(price * qty, 2)
    if cost > acct.cash:
        _record_order(
            db, acct, ds, clock, expiry=expiry, strike=strike, option_type=option_type, side="buy", qty=qty,
            price=price, status="rejected", source=source, run_id=run_id, note="Insufficient cash",
        )  # fmt: skip
        db.commit()
        raise PaperError(f"Insufficient cash: this order needs Rs {cost:,.2f} and the account has Rs {acct.cash:,.2f}")

    pos = db.scalar(
        select(PaperPosition).where(
            PaperPosition.account_id == acct.id, PaperPosition.dataset_id == ds.id, PaperPosition.expiry == expiry,
            PaperPosition.strike == strike, PaperPosition.option_type == option_type,
        )
    )  # fmt: skip
    if pos is None:
        pos = PaperPosition(
            id=_hex(), account_id=acct.id, user_id=acct.user_id, dataset_id=ds.id, underlying=ds.underlying,
            expiry=expiry, strike=strike, option_type=option_type, qty=qty, avg_price=price, stop_pct=stop_pct,
            target_pct=target_pct, square_off=square_off, run_id=run_id, opened_at=clock,
        )  # fmt: skip
        db.add(pos)
    else:  # add to the position at the average price; new exit rules replace the old ones when given
        pos.avg_price = round((pos.avg_price * pos.qty + price * qty) / (pos.qty + qty), 4)
        pos.qty += qty
        pos.stop_pct = stop_pct if stop_pct is not None else pos.stop_pct
        pos.target_pct = target_pct if target_pct is not None else pos.target_pct
        pos.square_off = square_off or pos.square_off
    acct.cash = round(acct.cash - cost, 2)
    order = _record_order(
        db, acct, ds, clock, expiry=expiry, strike=strike, option_type=option_type, side="buy", qty=qty, price=price,
        status="filled", source=source, run_id=run_id,
    )  # fmt: skip
    db.commit()
    return order


def _close(
    db: Session, acct: PaperAccount, pos: PaperPosition, qty: int, price: float, when: datetime, reason: str
) -> PaperTrade:
    """Sell `qty` of a position at `price`: realise the P&L, move the cash, record the order and the trade."""
    ds = db.get(Dataset, pos.dataset_id)
    assert ds is not None
    gross = round((price - pos.avg_price) * qty, 2)
    costs = round(2 * BROKERAGE_PER_ORDER + TAX_PCT / 100 * (pos.avg_price * qty + price * qty), 2)
    trade = PaperTrade(
        id=_hex(), account_id=acct.id, user_id=acct.user_id, dataset_id=pos.dataset_id, underlying=pos.underlying,
        expiry=pos.expiry, strike=pos.strike, option_type=pos.option_type, qty=qty, entry_price=pos.avg_price,
        exit_price=price, entry_time=pos.opened_at, exit_time=when, gross_pnl=gross, costs=costs,
        net_pnl=round(gross - costs, 2), exit_reason=reason, run_id=pos.run_id,
    )  # fmt: skip
    db.add(trade)
    _record_order(
        db, acct, ds, when, expiry=pos.expiry, strike=pos.strike, option_type=pos.option_type, side="sell", qty=qty,
        price=price, status="filled", source="manual" if reason == "manual" else "auto", run_id=pos.run_id,
        note=None if reason == "manual" else f"Exit: {reason}",
    )  # fmt: skip
    acct.cash = round(acct.cash + price * qty - costs, 2)
    pos.qty -= qty
    if pos.qty <= 0:
        db.delete(pos)
    return trade


def sell(db: Session, book: PriceBook, acct: PaperAccount, position_id: str, lots: int | None = None) -> PaperTrade:
    """Sell to close (all of the position, or `lots` lots) at the market price."""
    ds, clock = _market(db, acct)
    pos = db.get(PaperPosition, position_id)
    if pos is None or pos.account_id != acct.id:
        raise PaperError("Position not found")
    if pos.dataset_id != ds.id:
        raise PaperConflict("This position belongs to another dataset than the one the clock replays")
    qty = pos.qty if lots is None else lots * ds.lot_size
    if qty > pos.qty:
        raise PaperError(f"You hold {pos.qty // ds.lot_size} lot(s); selling to open is not supported")
    price = book.price_at(pos.dataset_id, pos.expiry, pos.strike, pos.option_type, clock)
    if price is None:
        raise PaperError("That contract has no price at the market time")
    trade = _close(db, acct, pos, qty, price, clock, "manual")
    db.commit()
    return trade


def _exit_reason(pos: PaperPosition, price: float, t: datetime) -> str | None:
    if t.date() > pos.expiry:
        return "expiry"
    if pos.stop_pct is not None and price <= pos.avg_price * (1 - pos.stop_pct / 100):
        return "stop"
    if pos.target_pct is not None and price >= pos.avg_price * (1 + pos.target_pct / 100):
        return "target"
    if pos.square_off:
        hh, mm = pos.square_off.split(":")
        if t.date() >= pos.opened_at.date() and t.time() >= time(int(hh), int(mm)):
            return "squareoff"
    return None


def advance(db: Session, book: PriceBook, acct: PaperAccount, candles: int) -> tuple[list[PaperTrade], bool]:
    """Move the market clock forward by `candles` candles, running exits on every candle. Returns (exits, at_end)."""
    ds, clock = _market(db, acct)
    tl = book.timeline(ds.id)
    start = int(tl.searchsorted(pd.Timestamp(clock), side="right"))
    stop = min(start + candles, len(tl))
    closed: list[PaperTrade] = []
    has_positions = db.scalar(
        select(func.count()).select_from(PaperPosition).where(PaperPosition.account_id == acct.id)
    )
    if start >= len(tl):
        return closed, True
    steps = range(start, stop) if has_positions else [stop - 1]  # nothing to check: jump straight there
    for i in steps:
        t = _t(tl.iloc[i])
        acct.clock_time = t
        for pos in list(db.scalars(select(PaperPosition).where(PaperPosition.account_id == acct.id))):
            price = book.price_at(pos.dataset_id, pos.expiry, pos.strike, pos.option_type, t)
            if price is None:
                continue
            reason = _exit_reason(pos, price, t)
            if reason:
                closed.append(_close(db, acct, pos, pos.qty, price, t, reason))
    db.commit()
    return closed, acct.clock_time is not None and acct.clock_time >= _t(tl.iloc[-1])


# ---- from an AI trade plan ---------------------------------------------------------------------
def buy_from_plan(
    db: Session, book: PriceBook, acct: PaperAccount, run: PipelineRun, option_type: str
) -> tuple[PaperOrder, list[str]]:
    """Open a paper position that follows an AI run's trade plan for the chosen side (CE or PE)."""
    risk = next((s for s in run.steps if s.get("name") == "risk"), {})
    plan = (risk.get("output") or {}).get("trade_plan")
    if not plan:
        raise PaperConflict("This run has no finished trade plan yet")
    action = plan.get("bullish_signal_action" if option_type == "CE" else "bearish_signal_action")
    if not action:
        raise PaperConflict(f"The plan has no {option_type} entry")
    if not str(action).lower().startswith("buy"):
        raise PaperConflict(f"The plan says '{action}': selling to open is not supported in paper trading")

    notes: list[str] = []
    if acct.dataset_id != run.dataset_id or acct.clock_time is None:
        start_clock(db, book, acct, run.dataset_id, None)
        notes.append("The market clock was started on the dataset this plan was built on.")
    ds, clock = _market(db, acct)

    listed = book.listed_expiries(ds.id, clock)
    if not listed:
        raise PaperError("No expiry is available at the market time")
    wanted = date.fromisoformat(plan["expiry_date"]) if plan.get("expiry_date") else None
    expiry = wanted if wanted in listed else listed[0]
    if wanted != expiry:
        notes.append(f"The plan's expiry {wanted or '(none)'} is not in this dataset; used {expiry}.")

    chain = book.chain_at(ds.id, expiry, clock)
    chain = chain[chain["option_type"] == option_type].reset_index(drop=True)
    spot = book.spot_at(ds.id, clock)
    if chain.empty or spot is None:
        raise PaperError("There are no prices for that expiry at the market time")
    s = plan.get("strike") or {}
    atm = int((chain["strike"] - spot).abs().to_numpy().argmin())
    if s.get("mode") == "offset":
        idx = min(max(atm + int(s.get("offset") or 0), 0), len(chain) - 1)
    elif s.get("mode") == "nearest_premium" and s.get("premium"):
        idx = int((chain["close"] - float(s["premium"])).abs().to_numpy().argmin())
    else:
        idx = atm
    strike = float(chain["strike"].iloc[idx])
    order = buy(
        db, book, acct, expiry=expiry, strike=strike, option_type=option_type, lots=int(plan.get("lots") or 1),
        stop_pct=plan.get("stop_loss_pct"), target_pct=plan.get("target_pct"), square_off=plan.get("square_off"),
        run_id=run.id, source="plan",
    )  # fmt: skip
    return order, notes
