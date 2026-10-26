from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import Cfg, CurrentUser, Db
from app.core.models import PaperAccount, PaperOrder, PaperTrade, PipelineRun
from app.data.models import Dataset
from app.paper import service
from app.paper.prices import PriceBook, get_book
from app.paper.service import PaperConflict, PaperError
from app.schemas.paper import (
    AccountOut,
    AdvanceIn,
    AdvanceOut,
    ChainOut,
    ChainRow,
    ClockStartIn,
    CloseIn,
    ExpiriesOut,
    FromPlanIn,
    FromPlanOut,
    OrderIn,
    OrderOut,
    PnlDay,
    PnlGroup,
    PnlOut,
    PnlSummary,
    PositionOut,
    ResetIn,
    TradeOut,
)

router = APIRouter(prefix="/paper", tags=["paper trading"])


def _fail(e: Exception) -> HTTPException:
    if isinstance(e, PaperConflict):
        return HTTPException(409, str(e))
    if isinstance(e, LookupError):
        return HTTPException(404, str(e))
    return HTTPException(400, str(e))


def _account(db: Db, user: CurrentUser) -> PaperAccount:
    return service.get_account(db, user.id)


def _out(db: Db, book: PriceBook, acct: PaperAccount) -> AccountOut:
    ds = db.get(Dataset, acct.dataset_id) if acct.dataset_id else None
    s = service.summary(db, book, acct)
    return AccountOut(
        **s,
        dataset_name=ds.name if ds else None,
        underlying=ds.underlying if ds else None,
        lot_size=ds.lot_size if ds else None,
    )


@router.get("/account", response_model=AccountOut, summary="Your paper account (created on first use)")
def get_account(db: Db, settings: Cfg, user: CurrentUser) -> AccountOut:
    try:
        return _out(db, get_book(settings.storage_dir), _account(db, user))
    except (PaperError, LookupError) as e:
        raise _fail(e) from e


@router.post("/account/reset", response_model=AccountOut, summary="Wipe positions, orders and trades and start over")
def reset_account(req: ResetIn, db: Db, settings: Cfg, user: CurrentUser) -> AccountOut:
    acct = service.reset_account(db, _account(db, user), req.starting_balance)
    return _out(db, get_book(settings.storage_dir), acct)


@router.post(
    "/clock/start", response_model=AccountOut, summary="Choose the dataset the market replays and set the clock"
)
def start_clock(req: ClockStartIn, db: Db, settings: Cfg, user: CurrentUser) -> AccountOut:
    book = get_book(settings.storage_dir)
    try:
        acct = service.start_clock(db, book, _account(db, user), req.dataset_id, req.at)
        return _out(db, book, acct)
    except (PaperError, LookupError) as e:
        raise _fail(e) from e


@router.post(
    "/clock/advance", response_model=AdvanceOut, summary="Move the market forward; stop/target/square-off/expiry run"
)
def advance(req: AdvanceIn, db: Db, settings: Cfg, user: CurrentUser) -> AdvanceOut:
    book = get_book(settings.storage_dir)
    acct = _account(db, user)
    try:
        exits, at_end = service.advance(db, book, acct, req.candles)
    except (PaperError, LookupError) as e:
        raise _fail(e) from e
    return AdvanceOut(
        account=_out(db, book, acct),
        exits=[TradeOut.model_validate(t, from_attributes=True) for t in exits],
        at_end=at_end,
    )


@router.get("/expiries", response_model=ExpiriesOut, summary="Expiries available at the market time")
def expiries(db: Db, settings: Cfg, user: CurrentUser) -> ExpiriesOut:
    acct = _account(db, user)
    if not acct.dataset_id or acct.clock_time is None:
        raise HTTPException(400, "Start the market clock first")
    try:
        found = get_book(settings.storage_dir).listed_expiries(acct.dataset_id, acct.clock_time)
    except LookupError as e:
        raise _fail(e) from e
    return ExpiriesOut(dataset_id=acct.dataset_id, clock_time=acct.clock_time, expiries=found)


@router.get("/chain", response_model=ChainOut, summary="Option prices of one expiry at the market time")
def chain(expiry: date, db: Db, settings: Cfg, user: CurrentUser) -> ChainOut:
    acct = _account(db, user)
    try:
        ds, clock = service._market(db, acct)
        book = get_book(settings.storage_dir)
        df = book.chain_at(ds.id, expiry, clock)
    except (PaperError, LookupError) as e:
        raise _fail(e) from e
    rows = [
        ChainRow(
            strike=float(strike),  # type: ignore[arg-type]
            ce=float(g.loc[g["option_type"] == "CE", "close"].iloc[0]) if (g["option_type"] == "CE").any() else None,
            pe=float(g.loc[g["option_type"] == "PE", "close"].iloc[0]) if (g["option_type"] == "PE").any() else None,
        )
        for strike, g in df.groupby("strike")
    ]
    return ChainOut(
        dataset_id=ds.id, underlying=ds.underlying, expiry=expiry, clock_time=clock, spot=book.spot_at(ds.id, clock),
        lot_size=ds.lot_size, rows=rows,
    )  # fmt: skip


@router.get("/positions", response_model=list[PositionOut], summary="Open positions marked to the market time")
def positions(db: Db, settings: Cfg, user: CurrentUser) -> list[PositionOut]:
    acct = _account(db, user)
    book = get_book(settings.storage_dir)
    out = []
    for m in service.marks(db, book, acct):
        p = m.position
        ds = db.get(Dataset, p.dataset_id)
        lot = ds.lot_size if ds else 1
        out.append(
            PositionOut(
                id=p.id,
                underlying=p.underlying,
                expiry=p.expiry,
                strike=p.strike,
                option_type=p.option_type,
                qty=p.qty,
                lots=max(1, p.qty // lot),
                avg_price=round(p.avg_price, 2),
                mark_price=m.price,
                unrealized_pnl=m.unrealized,
                stop_pct=p.stop_pct,
                target_pct=p.target_pct,
                square_off=p.square_off,
                run_id=p.run_id,
                opened_at=p.opened_at,
            )  # fmt: skip
        )
    return out


@router.get("/orders", response_model=list[OrderOut], summary="Order history, newest first")
def orders(db: Db, user: CurrentUser, limit: int = Query(100, ge=1, le=500)) -> list[OrderOut]:
    acct = _account(db, user)
    rows = db.scalars(
        select(PaperOrder).where(PaperOrder.account_id == acct.id).order_by(PaperOrder.created_at.desc()).limit(limit)
    )
    return [OrderOut.model_validate(r, from_attributes=True) for r in rows]


def _in_range(q: Any, date_from: date | None, date_to: date | None) -> Any:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from must not be after date_to")
    if date_from:
        q = q.where(PaperTrade.exit_time >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.where(PaperTrade.exit_time < datetime.combine(date_to + timedelta(days=1), time.min))
    return q


@router.get("/trades", response_model=list[TradeOut], summary="Closed trades with realised P&L, newest first")
def trades(
    db: Db,
    user: CurrentUser,
    limit: int = Query(200, ge=1, le=2000),
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[TradeOut]:
    """Closed trades; date_from / date_to (inclusive) filter on the day the trade was closed (market-clock time)."""
    acct = _account(db, user)
    q = select(PaperTrade).where(PaperTrade.account_id == acct.id)
    q = _in_range(q, date_from, date_to)
    rows = db.scalars(q.order_by(PaperTrade.exit_time.desc()).limit(limit))
    return [TradeOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/orders", response_model=OrderOut, status_code=201, summary="Buy an option at the market price")
def place_order(req: OrderIn, db: Db, settings: Cfg, user: CurrentUser) -> OrderOut:
    book = get_book(settings.storage_dir)
    acct = _account(db, user)
    try:
        if req.dataset_id and (acct.dataset_id != req.dataset_id or acct.clock_time is None):
            service.start_clock(db, book, acct, req.dataset_id, None)
        order = service.buy(
            db, book, acct, expiry=req.expiry, strike=req.strike, option_type=req.option_type, lots=req.lots,
            stop_pct=req.stop_pct, target_pct=req.target_pct,
        )  # fmt: skip
    except (PaperError, LookupError) as e:
        raise _fail(e) from e
    return OrderOut.model_validate(order, from_attributes=True)


@router.post("/positions/{position_id}/close", response_model=TradeOut, summary="Sell to close at the market price")
def close_position(position_id: str, req: CloseIn, db: Db, settings: Cfg, user: CurrentUser) -> TradeOut:
    try:
        trade = service.sell(db, get_book(settings.storage_dir), _account(db, user), position_id, req.lots)
    except (PaperError, LookupError) as e:
        raise _fail(e) from e
    return TradeOut.model_validate(trade, from_attributes=True)


@router.post("/from-plan", response_model=FromPlanOut, status_code=201, summary="Paper-trade the plan of an AI run")
def from_plan(req: FromPlanIn, db: Db, settings: Cfg, user: CurrentUser) -> FromPlanOut:
    run = db.get(PipelineRun, req.run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "Run not found")
    book = get_book(settings.storage_dir)
    acct = _account(db, user)
    try:
        order, notes = service.buy_from_plan(db, book, acct, run, req.option_type)
    except (PaperError, LookupError) as e:
        raise _fail(e) from e
    return FromPlanOut(
        order=OrderOut.model_validate(order, from_attributes=True), account=_out(db, book, acct), notes=notes
    )


def _groups(rows: list[PaperTrade], key: Any) -> list[PnlGroup]:
    out: dict[str, list[float]] = {}
    for t in rows:
        out.setdefault(key(t), []).append(t.net_pnl)
    return sorted(
        (PnlGroup(key=k, trades=len(v), net_pnl=round(sum(v), 2)) for k, v in out.items()), key=lambda g: -g.net_pnl
    )


@router.get("/pnl", response_model=PnlOut, summary="Realised P&L of closed trades for a date or a date range")
def pnl(db: Db, user: CurrentUser, date_from: date | None = None, date_to: date | None = None) -> PnlOut:
    """Closed trades only (unrealised P&L of open positions is not included). A single day is date_from = date_to."""
    acct = _account(db, user)
    first, last = db.execute(
        select(func.min(PaperTrade.exit_time), func.max(PaperTrade.exit_time)).where(PaperTrade.account_id == acct.id)
    ).one()
    q = _in_range(select(PaperTrade).where(PaperTrade.account_id == acct.id), date_from, date_to)
    rows = list(db.scalars(q.order_by(PaperTrade.exit_time, PaperTrade.id)))

    nets = [t.net_pnl for t in rows]
    wins, losses = [n for n in nets if n > 0], [n for n in nets if n < 0]
    peak = running = drawdown = 0.0
    for n in nets:
        running += n
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
    summary = PnlSummary(
        net_pnl=round(sum(nets), 2),
        gross_pnl=round(sum(t.gross_pnl for t in rows), 2),
        costs=round(sum(t.costs for t in rows), 2),
        trades=len(rows),
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=round(len(wins) / len(rows) * 100, 1) if rows else None,
        avg_win=round(sum(wins) / len(wins), 2) if wins else None,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else None,
        profit_factor=round(sum(wins) / abs(sum(losses)), 2) if losses else None,
        best_trade=round(max(nets), 2) if nets else None,
        worst_trade=round(min(nets), 2) if nets else None,
        max_drawdown=round(drawdown, 2),
    )
    by_day: dict[date, list[float]] = {}
    for t in rows:
        by_day.setdefault(t.exit_time.date(), []).append(t.net_pnl)
    daily, cumulative = [], 0.0
    for d in sorted(by_day):
        cumulative += sum(by_day[d])
        daily.append(
            PnlDay(date=d, trades=len(by_day[d]), net_pnl=round(sum(by_day[d]), 2), cumulative=round(cumulative, 2))
        )
    return PnlOut(
        date_from=date_from,
        date_to=date_to,
        available_from=first.date() if first else None,
        available_to=last.date() if last else None,
        summary=summary,
        daily=daily,
        by_exit_reason=_groups(rows, lambda t: t.exit_reason),
        by_option_type=_groups(rows, lambda t: t.option_type),
    )
