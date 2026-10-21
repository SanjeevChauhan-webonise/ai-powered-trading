import numpy as np
import pandas as pd
import pytest

from app.engine import indicators as ind
from tests.engine_helpers import make_underlying


def _df(closes: list[float]) -> pd.DataFrame:
    return make_underlying(closes)


def test_sma_and_bollinger() -> None:
    df = _df([1, 2, 3, 4, 5, 6])
    assert ind.compute("sma", df, {"period": 5})["value"].iloc[4:].tolist() == [3.0, 4.0]
    b = ind.compute("bollinger", df, {"period": 5, "std": 2})
    assert b["mid"].iloc[4] == 3.0
    assert b["upper"].iloc[4] == pytest.approx(3 + 2 * np.sqrt(2))  # population std of 1..5
    assert b["lower"].iloc[4] == pytest.approx(3 - 2 * np.sqrt(2))
    assert np.isnan(b["mid"].iloc[3])


def test_ema_recurrence() -> None:
    closes = [10, 11, 12, 11, 13, 14, 13, 15.0]
    got = ind.compute("ema", _df(closes), {"period": 3})["value"]
    alpha, ref = 2 / 4, [closes[0]]
    for c in closes[1:]:
        ref.append(alpha * c + (1 - alpha) * ref[-1])
    assert got.iloc[:2].isna().all()
    np.testing.assert_allclose(got.iloc[2:], ref[2:])


def test_rsi_wilder_reference_values() -> None:
    # classic Wilder/StockCharts RSI(14) example data; expected values computed with an independent
    # plain-python Wilder loop (published 70.53... differ by ~0.07 because they use unrounded closes)
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
              45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]  # fmt: skip
    r = ind.compute("rsi", _df(closes), {"period": 14})["value"]
    assert r.iloc[:14].isna().all()
    np.testing.assert_allclose(r.iloc[14:20], [70.46, 66.25, 66.48, 69.35, 66.29, 57.92], atol=0.01)


def test_rsi_extremes() -> None:
    up = ind.compute("rsi", _df([float(i) for i in range(1, 30)]), {"period": 14})["value"]
    assert up.iloc[-1] == 100.0


def test_atr_wilder() -> None:
    df = pd.DataFrame(
        {"timestamp": pd.date_range("2024-01-01", periods=6, freq="min"),
         "high": [10, 12, 13, 12, 14, 15.0], "low": [8, 9, 11, 10, 11, 13.0],
         "close": [9, 11, 12, 11, 13, 14.0], "open": 9.0, "volume": 1}
    )  # fmt: skip
    tr = [2, 3, 2, 2, 3, 2.0]  # tr[0]=h-l; then max(h-l,|h-pc|,|l-pc|)
    seed = np.mean(tr[:3])
    ref = [seed]
    for t in tr[3:]:
        ref.append((ref[-1] * 2 + t) / 3)
    got = ind.compute("atr", df, {"period": 3})["value"]
    assert got.iloc[:2].isna().all()
    np.testing.assert_allclose(got.iloc[2:], ref)


def test_macd_relations() -> None:
    closes = [100 + np.sin(i / 3) * 5 + i * 0.1 for i in range(80)]
    m = ind.compute("macd", _df(closes))
    fast = pd.Series(closes).ewm(span=12, adjust=False).mean()
    slow = pd.Series(closes).ewm(span=26, adjust=False).mean()
    valid = m["macd"].notna()
    np.testing.assert_allclose(m["macd"][valid], (fast - slow)[valid])
    np.testing.assert_allclose(m["hist"].dropna(), (m["macd"] - m["signal"]).dropna())
    assert m["signal"].first_valid_index() == 25 + 8


def test_vwap_resets_daily() -> None:
    d1 = make_underlying([100.0, 102.0, 104.0], "2024-01-01 09:15")
    d2 = make_underlying([200.0, 210.0], "2024-01-02 09:15")
    df = pd.concat([d1, d2], ignore_index=True)
    v = ind.compute("vwap", df)["value"]
    tp0 = (df["high"][0] + df["low"][0] + df["close"][0]) / 3
    tp3 = (df["high"][3] + df["low"][3] + df["close"][3]) / 3
    assert v[0] == pytest.approx(tp0)
    assert v[3] == pytest.approx(tp3)  # reset on day 2
    assert 100 < v[2] < 105


def test_supertrend_direction() -> None:
    up = [100 + i for i in range(30)]
    down = [129 - 3 * i for i in range(15)]
    st = ind.compute("supertrend", _df([float(c) for c in up + down]), {"period": 5, "multiplier": 2})
    assert st["direction"].iloc[25] == 1 and st["value"].iloc[25] < up[25]
    assert st["direction"].iloc[-1] == -1 and st["value"].iloc[-1] > down[-1]


@pytest.mark.parametrize("name", sorted(ind.REGISTRY))
def test_indicators_are_causal(name: str) -> None:
    rng = np.random.default_rng(0)
    closes = list(100 + np.cumsum(rng.normal(0, 1, 120)))
    df = _df(closes)
    full = ind.compute(name, df)
    k = 70
    part = ind.compute(name, df.iloc[:k].copy())
    pd.testing.assert_frame_equal(full.iloc[:k], part, check_exact=False)


def test_param_validation() -> None:
    with pytest.raises(ValueError, match="no params"):
        ind.resolve_params("ema", {"length": 5})
    with pytest.raises(ValueError, match="> 0"):
        ind.resolve_params("ema", {"period": 0})
    with pytest.raises(ValueError, match="Unknown"):
        ind.resolve_params("nope", {})
