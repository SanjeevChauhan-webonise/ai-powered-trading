"""Turn the user's rupee limits into lots and stop/target percentages. Pure code; LLMs never compute these numbers.

Assumes max_loss and target_profit are per trade and that the option is bought (premium is the risk). Entry premium is
estimated from the dataset (median ATM premium at the first candle after entry_start), so real fills will differ.
"""

import math
from datetime import date, timedelta
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from app.schemas.strategy import StrategySpec

DEFAULT_STOP_LOSS_PCT = 20.0
MIN_STOP_LOSS_PCT = 5.0


class Sizing(BaseModel):
    entry_premium: float | None
    lot_size: int
    lots: int
    quantity: int
    stop_loss_pct: float | None
    target_pct: float | None
    est_max_loss: float | None
    est_target_profit: float | None
    notes: list[str]


def expiry_kind(expiry: date) -> Literal["nearest_weekly", "monthly"]:
    """An expiry whose next-week date falls in another month is the month's last one, i.e. the monthly expiry."""
    return "monthly" if (expiry + timedelta(days=7)).month != expiry.month else "nearest_weekly"


def estimate_entry_premium(under: pd.DataFrame, opts: pd.DataFrame, spec: StrategySpec) -> float | None:
    """Median ATM (average of CE and PE) close at the first candle of each day at/after entry_start."""
    u = under[under["timestamp"].dt.time >= spec.risk.entry_start]
    first = u.groupby(u["timestamp"].dt.date).first()
    spot_at = dict(zip(first["timestamp"], first["close"], strict=True))
    o = opts[opts["timestamp"].isin(spot_at)]
    premiums: list[float] = []
    for ts, g in o.groupby("timestamp"):
        day = pd.Timestamp(ts).normalize()  # type: ignore[arg-type]
        live = sorted(e for e in g["expiry"].unique() if e >= day)
        if not live:
            continue
        if spec.instrument.expiry == "monthly":
            same_month = [e for e in live if (e.year, e.month) == (live[0].year, live[0].month)]
            expiry = same_month[-1]
        else:
            expiry = live[0]
        e = g[g["expiry"] == expiry]
        strike = e.iloc[(e["strike"] - spot_at[ts]).abs().argsort()[:1]]["strike"].iloc[0]
        premiums.append(float(e[e["strike"] == strike]["close"].mean()))
    return float(pd.Series(premiums).median()) if premiums else None


def apply_money_limits(
    spec: StrategySpec,
    premium: float | None,
    lot_size: int,
    max_loss: float | None,
    target_profit: float | None,
) -> tuple[StrategySpec, Sizing]:
    """Set lots, stop_loss_pct and target_pct so that a stopped-out trade loses about max_loss and a target hit earns
    about target_profit. Without a premium estimate (or limits) the spec's own values are kept."""
    notes: list[str] = []
    sl = spec.risk.stop_loss_pct
    lots, target = spec.lots, spec.risk.target_pct
    if premium and premium > 0 and (max_loss or target_profit):
        sl = sl or DEFAULT_STOP_LOSS_PCT
        if max_loss:
            lot_cost = premium * lot_size
            lots = math.floor(max_loss / (lot_cost * sl / 100))
            if lots < 1:
                lots = 1
                fit = max(max_loss / lot_cost * 100, MIN_STOP_LOSS_PCT)
                notes.append(
                    f"One lot at a {sl:g}% stop risks more than the limit; the stop was tightened to {fit:.1f}%."
                )
                sl = math.floor(fit * 10) / 10  # round down so one lot never exceeds the limit
                if lot_cost * sl / 100 > max_loss:
                    notes.append("Even the tightest stop leaves one lot above your max loss; reduce the limit or skip.")
        if target_profit:
            target = round(target_profit / (lots * lot_size * premium) * 100, 1)
    elif max_loss or target_profit:
        notes.append("No option premium could be estimated from the dataset, so the spec's own lots and %s were kept.")
    risk = spec.risk.model_copy(update={"stop_loss_pct": sl, "target_pct": target})
    out = spec.model_copy(update={"lots": lots, "risk": risk})
    qty = lots * lot_size
    ref = premium or 0.0
    return out, Sizing(
        entry_premium=round(premium, 2) if premium else None,
        lot_size=lot_size,
        lots=lots,
        quantity=qty,
        stop_loss_pct=sl,
        target_pct=target,
        est_max_loss=round(qty * ref * sl / 100, 2) if premium and sl else None,
        est_target_profit=round(qty * ref * target / 100, 2) if premium and target else None,
        notes=notes,
    )
