import pytest
from pydantic import ValidationError

from app.engine.templates import TEMPLATES
from app.schemas.strategy import StrategySpec
from tests.engine_helpers import make_spec

RULE = {"left": {"price": "close"}, "op": ">", "right": {"value": 1}}


def test_templates_valid_and_roundtrip() -> None:
    assert set(TEMPLATES) == {"ema_crossover", "rsi_reversal"}
    for spec in TEMPLATES.values():
        assert StrategySpec.model_validate_json(spec.model_dump_json()) == spec


def test_nested_conditions() -> None:
    spec = make_spec(entry_bullish={"all": [RULE, {"any": [RULE, RULE]}]})
    assert spec.entry_bullish is not None


@pytest.mark.parametrize(
    "patch, msg",
    [
        ({"entry_bullish": None, "entry_bearish": None}, "Define entry"),
        ({"signal_source": "option"}, "not supported"),
        ({"indicators": [{"id": "a", "type": "ema"}, {"id": "a", "type": "sma"}]}, "unique"),
        ({"indicators": [{"id": "a", "type": "ema", "params": {"bogus": 1}}]}, "no params"),
        ({"entry_bullish": {"left": {"indicator": "zzz"}, "op": ">", "right": {"value": 1}}}, "unknown indicator"),
        (
            {
                "indicators": [{"id": "m", "type": "macd"}],
                "entry_bullish": {"left": {"indicator": "m", "output": "nope"}, "op": ">", "right": {"value": 1}},
            },
            "no output",
        ),
        ({"entry_bullish": {"left": {"price": "close"}, "op": "between", "right": {"value": 1}}}, "between"),
        ({"entry_bullish": {"left": {"price": "close"}, "op": "between", "right": {"range": [5, 1]}}}, "between"),
        ({"entry_bullish": {"left": {"price": "close"}, "op": ">", "right": {"range": [1, 5]}}}, "range"),
        ({"risk": {"entry_start": "15:00", "entry_end": "10:00"}}, "entry_start"),
        ({"risk": {"stop_loss_pct": -5}}, "greater than 0"),
        ({"instrument": {"strike": {"mode": "nearest_premium"}}}, "premium"),
        ({"lots": 0}, "greater than or equal"),
        ({"surprise": 1}, "Extra"),
    ],
)
def test_invalid_specs(patch: dict, msg: str) -> None:  # type: ignore[type-arg]
    with pytest.raises((ValidationError, ValueError)) as e:
        make_spec(**patch)
    assert msg in str(e.value)


def test_between_ok() -> None:
    make_spec(entry_bullish={"left": {"price": "close"}, "op": "between", "right": {"range": [1, 5]}})
