from app.schemas.strategy import StrategySpec

EMA_CROSSOVER = StrategySpec.model_validate(
    {
        "name": "EMA Crossover",
        "description": "Buy CE when the fast EMA crosses above the slow EMA; buy PE when it crosses below.",
        "timeframe_minutes": 5,
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 9}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 21}},
        ],
        "entry_bullish": {
            "left": {"indicator": "ema_fast"},
            "op": "crosses_above",
            "right": {"indicator": "ema_slow"},
        },
        "entry_bearish": {
            "left": {"indicator": "ema_fast"},
            "op": "crosses_below",
            "right": {"indicator": "ema_slow"},
        },
        "exit_on_opposite_signal": True,
        "risk": {"stop_loss_pct": 20, "target_pct": 40},
    }
)

RSI_REVERSAL = StrategySpec.model_validate(
    {
        "name": "RSI Reversal",
        "description": "Buy CE when RSI crosses back above 30 (oversold reversal); buy PE when it crosses below 70.",
        "timeframe_minutes": 5,
        "indicators": [{"id": "rsi", "type": "rsi", "params": {"period": 14}}],
        "entry_bullish": {"left": {"indicator": "rsi"}, "op": "crosses_above", "right": {"value": 30}},
        "entry_bearish": {"left": {"indicator": "rsi"}, "op": "crosses_below", "right": {"value": 70}},
        "exit_on_opposite_signal": True,
        "risk": {"stop_loss_pct": 20, "target_pct": 40},
    }
)

TEMPLATES: dict[str, StrategySpec] = {"ema_crossover": EMA_CROSSOVER, "rsi_reversal": RSI_REVERSAL}
