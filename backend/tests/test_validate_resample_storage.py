from pathlib import Path

import pandas as pd

from app.data.normalize import NormalizeStats, normalize
from app.data.resample import resample
from app.data.storage import read_frame, write_frame
from app.data.validate import build_report, infer_timeframe_minutes
from app.schemas.data import ColumnMapping


def _candles(minutes: list[int]) -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01 09:15")
    n = len(minutes)
    return pd.DataFrame(
        {
            "timestamp": [base + pd.Timedelta(minutes=m) for m in minutes],
            "symbol": "X",
            "open": [float(i) + 10 for i in range(n)],
            "high": [float(i) + 12 for i in range(n)],
            "low": [float(i) + 9 for i in range(n)],
            "close": [float(i) + 11 for i in range(n)],
            "volume": [1] * n,
        }
    )


def test_gap_detection() -> None:
    df = _candles([0, 1, 2, 5, 6])  # minutes 3,4 missing
    report = build_report(df, NormalizeStats(input_rows=5, duplicates_removed=2))
    assert report.timeframe_minutes == 1
    assert report.gap_count == 1
    assert report.missing_candles == 2
    assert report.gap_samples[0].missing_candles == 2
    assert report.trading_days == 1
    assert any("duplicate" in w for w in report.warnings)


def test_infer_timeframe() -> None:
    assert infer_timeframe_minutes(_candles(list(range(0, 50, 5)))["timestamp"]) == 5


def test_resample_ohlcv() -> None:
    df = _candles(list(range(10)))
    out = resample(df, "underlying", 5)
    assert len(out) == 2
    first = out.iloc[0]
    assert first["timestamp"] == pd.Timestamp("2024-01-01 09:15")
    assert first["open"] == 10 and first["close"] == 15 and first["high"] == 16 and first["low"] == 9
    assert first["volume"] == 5


def test_resample_options_keeps_contracts_separate() -> None:
    ts = pd.date_range("2024-01-01 09:15", periods=4, freq="min").tolist() * 2
    df = pd.DataFrame(
        {
            "timestamp": ts, "underlying": "N", "expiry": pd.Timestamp("2024-01-04"),
            "strike": [100.0] * 4 + [200.0] * 4, "option_type": "CE",
            "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1, "oi": 5.0,
        }
    )  # fmt: skip
    out = resample(df, "options", 2)
    assert len(out) == 4
    assert out["volume"].tolist() == [2, 2, 2, 2]


def test_resample_rejects_finer() -> None:
    import pytest

    from app.data.normalize import DataError

    with pytest.raises(DataError):
        resample(_candles(list(range(0, 50, 5))), "underlying", 3)


def test_parquet_roundtrip(tmp_path: Path) -> None:
    df, _ = normalize(_candles([0, 1, 2]), "underlying", ColumnMapping.standard("underlying"), "X")
    p = tmp_path / "a" / "underlying.parquet"
    write_frame(p, df)
    pd.testing.assert_frame_equal(read_frame(p), df)
