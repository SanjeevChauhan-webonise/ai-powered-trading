"""Historical data import from Upstox (https://upstox.com/developer/api-documentation).

Underlying candles come from the v3 historical-candle API (minute data since Jan 2022).
Option candles come from the expired-instruments API, which needs an Upstox Plus plan and only
lists expiries from roughly the last six months.
"""

import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

from app.data.normalize import DataError

log = logging.getLogger(__name__)

BASE_URL = "https://api.upstox.com"
INDEX_KEYS = {"NIFTY": "NSE_INDEX|Nifty 50", "BANKNIFTY": "NSE_INDEX|Nifty Bank"}
EXPIRED_INTERVALS = {1: "1minute", 3: "3minute", 5: "5minute", 15: "15minute", 30: "30minute"}
UNDERLYING_CHUNK_DAYS = 28  # v3 minute candles: max 1 month per request (1-15 min)
OPTION_CHUNK_DAYS = 7  # the expired-candle docs state no range limit, so stay conservative
OPTION_LOOKBACK_DAYS = 31  # a monthly contract lists for about a month before expiry
WEEKLY_LOOKBACK_DAYS = 7
MIN_REQUEST_GAP = 0.1  # limit is 50/s, 500/min, 2000/30min; ~0.1s keeps well under the per-minute cap
MAX_RETRIES = 4


class UpstoxError(DataError):
    """Upstox rejected or failed a request."""


class UpstoxClient:
    def __init__(self, token: str, *, client: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise UpstoxError("UPSTOX_ACCESS_TOKEN is not set")
        self._http = client or httpx.Client(base_url=BASE_URL, timeout=30.0)
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._sleep = sleep
        self._last = 0.0

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            wait = MIN_REQUEST_GAP - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            resp = self._http.get(path, params=params, headers=self._headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < MAX_RETRIES:
                    self._sleep(2.0**attempt)
                    continue
            if resp.status_code >= 400:
                raise UpstoxError(f"Upstox {resp.status_code} on {path}: {_error_text(resp)}")
            body = resp.json()
            if body.get("status") != "success":
                raise UpstoxError(f"Upstox error on {path}: {body}")
            return body["data"]
        raise UpstoxError(f"Upstox request failed after retries: {path}")

    def underlying_candles(self, instrument_key: str, interval: int, start: date, end: date) -> list[list[Any]]:
        out: list[list[Any]] = []
        for lo, hi in _windows(start, end, UNDERLYING_CHUNK_DAYS):
            path = f"/v3/historical-candle/{quote(instrument_key, safe='')}/minutes/{interval}/{hi}/{lo}"
            out += self._get(path)["candles"]
        return out

    def expiries(self, instrument_key: str) -> list[date]:
        data = self._get("/v2/expired-instruments/expiries", {"instrument_key": instrument_key})
        return sorted(date.fromisoformat(d) for d in data)

    def option_contracts(self, instrument_key: str, expiry: date) -> list[dict[str, Any]]:
        params = {"instrument_key": instrument_key, "expiry_date": expiry.isoformat()}
        contracts: list[dict[str, Any]] = self._get("/v2/expired-instruments/option/contract", params)
        return contracts

    def expired_candles(self, expired_key: str, interval: int, start: date, end: date) -> list[list[Any]]:
        out: list[list[Any]] = []
        for lo, hi in _windows(start, end, OPTION_CHUNK_DAYS):
            key, unit = quote(expired_key, safe=""), EXPIRED_INTERVALS[interval]
            path = f"/v2/expired-instruments/historical-candle/{key}/{unit}/{hi}/{lo}"
            out += self._get(path)["candles"]
        return out


def _error_text(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("errors") or resp.json())
    except ValueError:
        return resp.text[:200]


def _windows(start: date, end: date, days: int) -> list[tuple[date, date]]:
    """Inclusive (from, to) windows of at most `days` days covering start..end."""
    out, lo = [], start
    while lo <= end:
        hi = min(lo + timedelta(days=days - 1), end)
        out.append((lo, hi))
        lo = hi + timedelta(days=1)
    return out


def _candle_frame(candles: list[list[Any]]) -> pd.DataFrame:
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return df


def fetch_underlying(client: UpstoxClient, underlying: str, interval: int, start: date, end: date) -> pd.DataFrame:
    """Underlying candles in the standard upload schema (timestamp naive IST)."""
    key = INDEX_KEYS[underlying]
    candles = client.underlying_candles(key, interval, start, end)
    if not candles:
        raise UpstoxError(f"Upstox returned no {underlying} candles for {start}..{end}")
    df = _candle_frame(candles).drop(columns="oi")
    df.insert(1, "symbol", underlying)
    return df


def _pick_strikes(contracts: list[dict[str, Any]], reference: float, n_strikes: int) -> list[dict[str, Any]]:
    strikes = sorted({float(c["strike_price"]) for c in contracts})
    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - reference))
    keep = set(strikes[max(0, atm - n_strikes) : atm + n_strikes + 1])
    return [c for c in contracts if float(c["strike_price"]) in keep]


def fetch_expiry_options(
    client: UpstoxClient,
    underlying: str,
    underlying_df: pd.DataFrame,
    expiry: date,
    interval: int,
    start: date,
    n_strikes: int,
    option_types: tuple[str, ...] = ("CE", "PE"),
    expiry_type: str = "all",
) -> tuple[pd.DataFrame | None, int]:
    """Option candles for one expiry, ATM +/- n_strikes. Returns (frame or None if no data, lot_size).

    option_types limits to CE and/or PE; expiry_type ("all", "weekly", "monthly") keeps only matching contracts.
    """
    key = INDEX_KEYS[underlying]
    lo = max(start, expiry - timedelta(days=OPTION_LOOKBACK_DAYS))
    week = underlying_df[
        (underlying_df["timestamp"].dt.date >= expiry - timedelta(days=7))
        & (underlying_df["timestamp"].dt.date <= expiry)
    ]
    if week.empty:
        log.warning("no underlying candles near expiry %s; skipping", expiry)
        return None, 1
    wanted = [
        c
        for c in client.option_contracts(key, expiry)
        if c["instrument_type"] in option_types
        and (expiry_type == "all" or bool(c.get("weekly")) == (expiry_type == "weekly"))
    ]
    if not wanted:
        return None, 1
    contracts = _pick_strikes(wanted, float(week["close"].median()), n_strikes)
    frames: list[pd.DataFrame] = []
    lot_size = 1
    for c in contracts:
        lot_size = int(c.get("lot_size") or lot_size)
        # weekly contracts only trade ~a week; asking for a month would waste ~4 calls per contract
        c_lo = max(lo, expiry - timedelta(days=WEEKLY_LOOKBACK_DAYS)) if c.get("weekly") else lo
        candles = client.expired_candles(c["instrument_key"], interval, c_lo, expiry)
        if not candles:
            continue
        df = _candle_frame(candles)
        df["underlying"] = underlying
        df["expiry"] = pd.Timestamp(expiry)
        df["strike"] = float(c["strike_price"])
        df["option_type"] = c["instrument_type"]
        frames.append(df)
    log.info("fetched expiry %s: %d contracts", expiry, len(contracts))
    return (pd.concat(frames, ignore_index=True) if frames else None), lot_size


def list_expiries(client: UpstoxClient, underlying: str, start: date, end: date, last: int | None = None) -> list[date]:
    """Expiries in start..end; `last` keeps only the most recent N."""
    expiries = [e for e in client.expiries(INDEX_KEYS[underlying]) if start <= e <= end]
    if last:
        expiries = expiries[-last:]
    if not expiries:
        raise UpstoxError(
            f"No expired {underlying} expiries between {start} and {end} (Upstox lists only ~6 months of history)"
        )
    return expiries


def fetch_options(
    client: UpstoxClient,
    underlying: str,
    underlying_df: pd.DataFrame,
    interval: int,
    start: date,
    end: date,
    n_strikes: int,
) -> tuple[pd.DataFrame, int]:
    """Option candles for all expiries in start..end. Returns (frame, lot_size)."""
    frames: list[pd.DataFrame] = []
    lot_size = 1
    for expiry in list_expiries(client, underlying, start, end):
        df, lot = fetch_expiry_options(client, underlying, underlying_df, expiry, interval, start, n_strikes)
        if df is not None:
            frames.append(df)
            lot_size = lot
    if not frames:
        raise UpstoxError("Upstox returned no option candles")
    return pd.concat(frames, ignore_index=True), lot_size
