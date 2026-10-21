"""The final, human-readable trade plan assembled in code from the run's outputs. The user places orders themselves."""

from typing import Any

from app.engine.sizing import Sizing
from app.schemas.agents import RunRequest
from app.schemas.strategy import StrategySpec

# Largest max-loss-per-trade, as % of capital, that is comfortable for each experience level (a note, not a block)
LEVEL_MAX_RISK_PCT = {"beginner": 2.0, "advanced": 5.0, "expert": 10.0}


def risk_note(level: str, capital: float, max_loss: float | None) -> str | None:
    limit = LEVEL_MAX_RISK_PCT.get(level)
    if not (limit and max_loss and capital > 0) or max_loss / capital * 100 <= limit:
        return None
    return (
        f"Your max loss is {max_loss / capital * 100:.1f}% of capital. For a {level} profile we suggest keeping "
        f"risk per trade at or below {limit:g}% (about Rs {capital * limit / 100:,.0f})."
    )


DISCLAIMER = (
    "Educational research output, not financial advice. You place the orders yourself. Lots and stop/target are "
    "estimates from historical option premiums; actual fills, premiums and slippage will differ."
)


def build_trade_plan(
    req: RunRequest,
    underlying: str,
    spec: StrategySpec,
    sizing: Sizing | None,
    reasoning: dict[str, Any],
    verify: dict[str, Any],
    metrics: dict[str, Any],
    level: str = "advanced",
) -> dict[str, Any]:
    buy = spec.direction == "buy"
    r = spec.risk
    return {
        "underlying": underlying,
        "expiry_date": req.expiry.isoformat() if req.expiry else None,
        "expiry_type": spec.instrument.expiry,
        "strategy": spec.name,
        "bullish_signal_action": ("buy CE" if buy else "sell PE") if spec.entry_bullish else None,
        "bearish_signal_action": ("buy PE" if buy else "sell CE") if spec.entry_bearish else None,
        "strike": spec.instrument.strike.model_dump(),
        "entry_window": f"{r.entry_start:%H:%M}-{r.entry_end:%H:%M}",
        "square_off": f"{r.square_off:%H:%M}",
        "max_trades_per_day": r.max_trades_per_day,
        "lots": spec.lots,
        "quantity": sizing.quantity if sizing else None,
        "entry_premium_estimate": sizing.entry_premium if sizing else None,
        "stop_loss_pct": r.stop_loss_pct,
        "target_pct": r.target_pct,
        "trailing_sl_pct": r.trailing_sl_pct,
        "max_loss_per_trade": sizing.est_max_loss if sizing else None,
        "target_profit_per_trade": sizing.est_target_profit if sizing else None,
        "your_limits": {"capital": req.capital, "max_loss": req.max_loss, "target_profit": req.target_profit},
        "when_to_trade": reasoning.get("when_to_trade", ""),
        "reasons": reasoning.get("reasons", []),
        "assumptions": reasoning.get("assumptions", []),
        "explanation": reasoning.get("explanation", ""),
        "verification": {"verdict": verify.get("verdict"), "summary": verify.get("summary")},
        "backtest": {
            k: metrics.get(k) for k in ("num_trades", "win_rate_pct", "total_pnl", "max_drawdown_pct", "profit_factor")
        },
        "level": level,
        "notes": [
            *(sizing.notes if sizing else []),
            *([n] if (n := risk_note(level, req.capital, req.max_loss)) else []),
            *(["Beginner profile: at most 3 trades a day."] if level == "beginner" else []),
            DISCLAIMER,
        ],
    }
