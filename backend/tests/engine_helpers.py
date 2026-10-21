from typing import Any

import pandas as pd

from app.schemas.strategy import StrategySpec

T0 = "2024-01-01 09:15"
EXPIRY = pd.Timestamp("2024-01-04")
FLAT = (100.0, 100.0, 100.0, 100.0)


def timestamps(n: int, start: str = T0) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="min")


def make_underlying(closes: list[float], start: str = T0) -> pd.DataFrame:
    ts = timestamps(len(closes), start)
    opens = [closes[0], *closes[:-1]]
    return pd.DataFrame(
        {
            "timestamp": ts, "symbol": "X", "open": opens,
            "high": [max(o, c) + 0.5 for o, c in zip(opens, closes, strict=True)],
            "low": [min(o, c) - 0.5 for o, c in zip(opens, closes, strict=True)],
            "close": closes, "volume": 1000,
        }
    )  # fmt: skip


def make_options(
    n: int,
    ce: dict[int, tuple[float, float, float, float]] | None = None,
    pe: dict[int, tuple[float, float, float, float]] | None = None,
    strikes: dict[float, tuple[float, float]] | None = None,
    missing: dict[str, set[int]] | None = None,
    start: str = T0,
) -> pd.DataFrame:
    """Flat 100 premium unless overridden per candle index. `strikes` maps strike -> (ce_price, pe_price)."""
    ts = timestamps(n, start)
    rows: list[dict[str, Any]] = []
    for strike, (ce_p, pe_p) in (strikes or {100.0: (100.0, 100.0)}).items():
        for typ, over, base in (("CE", ce, ce_p), ("PE", pe, pe_p)):
            for i, t in enumerate(ts):
                if i in (missing or {}).get(typ, set()):
                    continue
                o, h, lo, c = (over or {}).get(i, (base, base, base, base)) if strike == 100.0 else (base,) * 4
                rows.append(
                    {"timestamp": t, "underlying": "X", "expiry": EXPIRY, "strike": strike, "option_type": typ,
                     "open": o, "high": h, "low": lo, "close": c, "volume": 1, "oi": 1.0}
                )  # fmt: skip
    return pd.DataFrame(rows)


def make_spec(**over: Any) -> StrategySpec:
    cross_up = {"left": {"price": "close"}, "op": "crosses_above", "right": {"value": 100}}
    cross_dn = {"left": {"price": "close"}, "op": "crosses_below", "right": {"value": 100}}
    base: dict[str, Any] = {
        "name": "test",
        "entry_bullish": cross_up,
        "entry_bearish": cross_dn,
        "risk": {"entry_start": "09:15", "stop_loss_pct": 20, "target_pct": 40},
        "costs": {"brokerage_per_order": 0, "tax_pct": 0},
    }
    for k, v in over.items():
        if k in ("risk", "costs", "instrument") and isinstance(v, dict):
            base[k] = {**base.get(k, {}), **v}
        else:
            base[k] = v
    return StrategySpec.model_validate(base)


# bullish cross at index 2 -> fill at index 3 open
CLOSES = [99.0, 99.0, 101.0] + [101.0] * 12
