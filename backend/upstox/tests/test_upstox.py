from datetime import date

import httpx
import pytest

from upstox import UpstoxClient, UpstoxError, fetch_options, fetch_underlying
from upstox.client import _windows


def _candle(ts: str, px: float) -> list:
    return [ts, px, px + 5, px - 5, px + 1, 100, 0]


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.raw_path.decode().split("?")[0]
    if path.startswith("/v3/historical-candle/NSE_INDEX%7CNifty%2050/minutes/5/"):
        return httpx.Response(200, json={"status": "success", "data": {"candles": [
            _candle("2025-04-10T09:15:00+05:30", 22000), _candle("2025-04-10T09:20:00+05:30", 22010),
        ]}})  # fmt: skip
    if path == "/v2/expired-instruments/expiries":
        return httpx.Response(200, json={"status": "success", "data": ["2025-04-17", "2025-06-26"]})
    if path == "/v2/expired-instruments/option/contract":
        rows = [
            {"instrument_key": f"NSE_FO|{s}{t}|17-04-2025", "strike_price": s, "instrument_type": t, "lot_size": 75}
            for s in (21900, 22000, 22100, 23000)
            for t in ("CE", "PE")
        ]
        return httpx.Response(200, json={"status": "success", "data": rows})
    if "/expired-instruments/historical-candle/" in path:
        return httpx.Response(200, json={"status": "success", "data": {"candles": [
            _candle("2025-04-10T09:15:00+05:30", 100),
        ]}})  # fmt: skip
    return httpx.Response(404, json={"errors": "nope"})


def _client(handler=_handler) -> UpstoxClient:
    http = httpx.Client(base_url="https://api.upstox.com", transport=httpx.MockTransport(handler))
    return UpstoxClient("tok", client=http, sleep=lambda _: None)


def test_windows_cover_range_without_overlap():
    w = _windows(date(2025, 1, 1), date(2025, 3, 1), 28)
    assert w[0][0] == date(2025, 1, 1) and w[-1][1] == date(2025, 3, 1)
    assert all((b[0] - a[1]).days == 1 for a, b in zip(w, w[1:], strict=False))
    assert all((hi - lo).days < 28 for lo, hi in w)


def test_missing_token():
    with pytest.raises(UpstoxError):
        UpstoxClient("")


def test_fetch_underlying_standard_schema():
    df = fetch_underlying(_client(), "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 10))
    assert list(df.columns) == ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
    assert df["timestamp"].iloc[0].hour == 9 and df["timestamp"].dt.tz is None
    assert (df["symbol"] == "NIFTY").all()


def test_fetch_options_picks_strikes_around_atm_and_filters_expiries():
    client = _client()
    under = fetch_underlying(client, "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 17))
    opts, lot = fetch_options(client, "NIFTY", under, 5, date(2025, 4, 10), date(2025, 4, 17), n_strikes=1)
    assert lot == 75
    assert sorted(opts["strike"].unique()) == [21900.0, 22000.0, 22100.0]  # 23000 excluded
    assert set(opts["option_type"]) == {"CE", "PE"}
    assert (opts["expiry"] == "2025-04-17").all()


def test_retries_then_raises_on_api_error():
    calls = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429)

    with pytest.raises(UpstoxError):
        _client(h).expiries("NSE_INDEX|Nifty 50")
    assert len(calls) == 5


def test_option_type_and_last_expiries_filters():
    from upstox import list_expiries

    client = _client()
    under = fetch_underlying(client, "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 17))
    opts, _ = fetch_options(client, "NIFTY", under, 5, date(2025, 4, 10), date(2025, 4, 17), n_strikes=1)
    from upstox import fetch_expiry_options

    ce, _ = fetch_expiry_options(client, "NIFTY", under, date(2025, 4, 17), 5, date(2025, 4, 10), 1, ("CE",))
    assert set(ce["option_type"]) == {"CE"} and len(opts) > len(ce)
    none, _ = fetch_expiry_options(
        client, "NIFTY", under, date(2025, 4, 17), 5, date(2025, 4, 10), 1, expiry_type="weekly"
    )
    assert none is None  # mock contracts carry no weekly flag
    assert list_expiries(client, "NIFTY", date(2025, 1, 1), date(2025, 12, 31), last=1) == [date(2025, 6, 26)]
