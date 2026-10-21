import pandas as pd

from app.data.normalize import NormalizeStats
from app.schemas.data import GapSample, QualityReport

MAX_GAP_SAMPLES = 10


def infer_timeframe_minutes(ts: pd.Series) -> int | None:
    """Most common spacing between consecutive candles within the same day."""
    u = ts.drop_duplicates().sort_values()
    if len(u) < 2:
        return None
    same_day = u.dt.date == u.shift().dt.date
    mins = (u.diff().dt.total_seconds() / 60)[same_day].round()
    mins = mins[mins > 0]
    if mins.empty:
        return 1440  # one candle per day
    return int(mins.mode().iloc[0])


def build_report(df: pd.DataFrame, stats: NormalizeStats) -> QualityReport:
    ts = df["timestamp"].drop_duplicates().sort_values().reset_index(drop=True)
    tf = infer_timeframe_minutes(ts)
    gaps: list[GapSample] = []
    missing = gap_count = 0
    if tf and tf < 1440:
        same_day = ts.dt.date == ts.shift().dt.date
        diff = ts.diff().dt.total_seconds() / 60
        gap_idx = ts.index[same_day & (diff > tf * 1.5)]
        gap_count = len(gap_idx)
        for i in gap_idx:
            n = int(round(diff[i] / tf)) - 1
            missing += n
            if len(gaps) < MAX_GAP_SAMPLES:
                gaps.append(GapSample(start=ts[i - 1], end=ts[i], missing_candles=n))

    warnings: list[str] = []
    if stats.duplicates_removed:
        warnings.append(f"{stats.duplicates_removed} duplicate candles removed (last kept)")
    if stats.bad_timestamps:
        warnings.append(f"{stats.bad_timestamps} rows dropped: unparseable timestamp")
    if stats.bad_rows:
        warnings.append(f"{stats.bad_rows} rows dropped: missing/non-numeric required values")
    if stats.invalid_ohlc:
        warnings.append(
            f"{stats.invalid_ohlc} rows dropped: invalid OHLC (high<low, open/close outside range, bad prices)"
        )
    if missing:
        warnings.append(f"{missing} missing candles across {gap_count} gaps")

    return QualityReport(
        input_rows=stats.input_rows,
        rows=len(df),
        bad_timestamps=stats.bad_timestamps,
        bad_rows=stats.bad_rows,
        invalid_ohlc_rows=stats.invalid_ohlc,
        duplicates_removed=stats.duplicates_removed,
        trading_days=int(ts.dt.date.nunique()),
        timeframe_minutes=tf,
        missing_candles=missing,
        gap_count=gap_count,
        gap_samples=gaps,
        warnings=warnings,
    )
