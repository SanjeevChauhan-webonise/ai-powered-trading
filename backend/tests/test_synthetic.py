import pandas as pd

from app.data.synthetic import SyntheticConfig, generate

CFG = SyntheticConfig(trading_days=3, n_strikes=3)


def test_deterministic() -> None:
    a = generate(CFG)
    b = generate(CFG)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])


def test_shapes_and_validity() -> None:
    under, opts = generate(CFG)
    assert len(under) == 3 * 375
    assert (under["high"] >= under[["open", "close"]].max(axis=1)).all()
    assert (under["low"] <= under[["open", "close"]].min(axis=1)).all()
    assert (opts["high"] >= opts[["open", "close"]].max(axis=1)).all()
    assert (opts["low"] <= opts[["open", "close"]].min(axis=1)).all()
    assert (opts["low"] > 0).all()
    assert set(opts["option_type"]) == {"CE", "PE"}
    assert (opts["expiry"].dt.normalize() >= opts["timestamp"].dt.normalize()).all()
    assert opts["strike"].nunique() >= 7
    assert not opts.duplicated(["timestamp", "expiry", "strike", "option_type"]).any()


def test_put_call_moneyness() -> None:
    _, opts = generate(CFG)
    first = opts[opts["timestamp"] == opts["timestamp"].min()]
    first = first[first["expiry"] == first["expiry"].min()]
    ce = first[first["option_type"] == "CE"].sort_values("strike")["close"]
    assert ce.is_monotonic_decreasing  # higher strike call is cheaper
