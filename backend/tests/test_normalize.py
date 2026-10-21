import pandas as pd
import pytest

from app.data.normalize import DataError, normalize
from app.schemas.data import ColumnMapping

MAP = ColumnMapping(
    timestamp="Date", open="O", high="H", low="L", close="C", volume="Vol",
    timestamp_format="%d-%m-%Y %H:%M",
)  # fmt: skip


def _raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": ["01-01-2024 09:16", "01-01-2024 09:15", "01-01-2024 09:15", "garbage", "01-01-2024 09:17", "01-01-2024 09:18"],
            "O": [101, 100, 100.5, 100, 102, 103],
            "H": [102, 101, 101, 101, 103, 102],  # last row: high < low
            "L": [100, 99, 99, 99, 101, 104],
            "C": [101.5, 100.5, 100.6, 100, 102.5, 103],
            "Vol": [10, 20, 30, 5, "x", 7],
        }
    )  # fmt: skip


def test_underlying_mapping_cleaning() -> None:
    df, stats = normalize(_raw(), "underlying", MAP, "NIFTY")
    assert list(df.columns) == ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
    assert stats.bad_timestamps == 1
    assert stats.invalid_ohlc == 1
    assert stats.duplicates_removed == 1
    assert df["timestamp"].is_monotonic_increasing
    assert (df["symbol"] == "NIFTY").all()
    dup = df[df["timestamp"] == pd.Timestamp("2024-01-01 09:15")]
    assert dup["close"].iloc[0] == 100.6  # last duplicate kept
    assert df["volume"].tolist() == [30, 10, 0]  # non-numeric volume -> 0


def test_timezone_aware_converted_to_local_naive() -> None:
    raw = pd.DataFrame({"t": ["2024-01-01T03:45:00Z"], "o": [1.0], "h": [2.0], "l": [0.5], "c": [1.5]})
    m = ColumnMapping(timestamp="t", open="o", high="h", low="l", close="c")
    df, _ = normalize(raw, "underlying", m, "X")
    assert df["timestamp"].iloc[0] == pd.Timestamp("2024-01-01 09:15")


def test_options_normalization() -> None:
    raw = pd.DataFrame(
        {
            "ts": ["2024-01-01 09:15"] * 3, "exp": ["2024-01-04"] * 3, "k": [22000, 22000, 22000],
            "cp": ["call", "PUT", "X"], "o": [1, 1, 1], "h": [2, 2, 2], "l": [0.5, 0.5, 0.5], "c": [1, 1, 1],
        }
    )  # fmt: skip
    m = ColumnMapping(
        timestamp="ts",
        open="o",
        high="h",
        low="l",
        close="c",
        expiry="exp",
        strike="k",
        option_type="cp",
    )
    df, stats = normalize(raw, "options", m, "NIFTY")
    assert sorted(df["option_type"]) == ["CE", "PE"]
    assert stats.bad_rows == 1
    assert (df["underlying"] == "NIFTY").all()


def test_missing_mapped_column_raises() -> None:
    with pytest.raises(DataError, match="not found"):
        normalize(_raw().drop(columns=["O"]), "underlying", MAP, "NIFTY")


def test_options_require_option_fields() -> None:
    with pytest.raises(DataError, match="required"):
        normalize(_raw(), "options", MAP, "NIFTY")
