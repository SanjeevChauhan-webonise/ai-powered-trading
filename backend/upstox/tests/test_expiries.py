import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.expiries import get_expiry_service
from app.main import app
from upstox.expiries import ExpiryError, ExpiryService, parse_instruments


def ms(y: int, m: int, d: int) -> int:  # 15:29:59 IST, as the exchange lists expiries
    return int((datetime(y, m, d, 9, 59, 59, tzinfo=UTC)).timestamp() * 1000)


def contract(under: str, expiry: int, weekly: bool, lot: int, typ: str = "CE", seg: str = "NSE_FO") -> dict:
    return {
        "segment": seg, "instrument_type": typ, "underlying_symbol": under, "expiry": expiry,
        "weekly": weekly, "lot_size": lot,
    }  # fmt: skip


RAW = gzip.compress(
    json.dumps(
        [
            contract("NIFTY", ms(2026, 11, 3), True, 65),
            contract("NIFTY", ms(2026, 11, 3), True, 65, "PE"),
            contract("NIFTY", ms(2026, 11, 9), True, 65),  # holiday-shifted weekly (a Monday)
            contract("NIFTY", ms(2026, 11, 23), False, 65),  # holiday-shifted monthly
            contract("NIFTY", ms(2026, 10, 1), True, 65),  # already expired
            contract("BANKNIFTY", ms(2026, 11, 23), False, 30),
            contract("FINNIFTY", ms(2026, 11, 3), True, 60),  # not tracked
            contract("NIFTY", ms(2026, 11, 3), True, 65, "FUT"),  # not an option
            {"segment": "NSE_EQ", "instrument_type": "EQ", "name": "X"},
        ]
    ).encode()
)
NOW = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


def service(tmp_path: Path, handler=None, clock=lambda: NOW, ttl: float = 3600) -> ExpiryService:
    handler = handler or (lambda r: httpx.Response(200, content=RAW))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ExpiryService(tmp_path / "exp.json", client=client, ttl=ttl, clock=clock)


def test_parse_keeps_only_nifty_banknifty_options():
    t = parse_instruments(RAW, NOW)
    assert t.lot_sizes == {"NIFTY": 65, "BANKNIFTY": 30}
    assert t.expiries["NIFTY"] == {"2026-10-01": True, "2026-11-03": True, "2026-11-09": True, "2026-11-23": False}
    assert t.expiries["BANKNIFTY"] == {"2026-11-23": False}


def test_upcoming_skips_past_and_flags_kind(tmp_path: Path):
    rows, table, stale = service(tmp_path).upcoming("NIFTY", 10, today=date(2026, 10, 21))
    assert [(r.date.isoformat(), r.kind, r.days) for r in rows] == [
        ("2026-11-03", "weekly", 13), ("2026-11-09", "weekly", 19), ("2026-11-23", "monthly", 33),
    ]  # fmt: skip
    assert not stale and table.lot_sizes["NIFTY"] == 65


def test_cache_used_then_stale_fallback_when_download_fails(tmp_path: Path):
    calls: list[int] = []
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503) if fail else httpx.Response(200, content=RAW)

    clock_now = [NOW]
    svc = service(tmp_path, handler, clock=lambda: clock_now[0], ttl=3600)
    svc.upcoming("NIFTY", 3)
    svc.upcoming("NIFTY", 3)
    assert len(calls) == 1  # second call served from memory
    clock_now[0] = NOW + timedelta(hours=7)
    fail = True
    _, _, stale = svc.upcoming("NIFTY", 3)
    assert stale and len(calls) == 2  # download failed, the old copy is returned and marked stale
    # a fresh process with no memory still finds the disk cache
    svc2 = service(tmp_path, handler, clock=lambda: clock_now[0])
    assert svc2.upcoming("NIFTY", 3)[2]


def test_no_cache_and_no_network_raises(tmp_path: Path):
    svc = service(tmp_path, lambda r: httpx.Response(500))
    with pytest.raises(ExpiryError):
        svc.upcoming("NIFTY", 3)


def test_kind_of_and_is_listed_use_cache_only(tmp_path: Path):
    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be used")

    cold = service(tmp_path / "cold", boom)
    assert cold.kind_of("NIFTY", date(2026, 11, 23)) is None and cold.is_listed("NIFTY", date(2026, 11, 23)) is None
    warm = service(tmp_path / "warm")
    warm.upcoming("NIFTY", 1)
    assert warm.kind_of("NIFTY", date(2026, 11, 23)) == "monthly"  # a Monday: the +7 days rule would say weekly
    assert warm.kind_of("NIFTY", date(2026, 11, 9)) == "weekly"
    assert warm.is_listed("NIFTY", date(2026, 11, 10)) is False


def test_expiries_endpoint(tmp_path: Path, client: TestClient):
    app.dependency_overrides[get_expiry_service] = lambda: service(tmp_path)
    try:
        c = client
        r = c.get("/expiries", params={"underlying": "BANKNIFTY", "count": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lot_size"] == 30 and body["stale"] is False
        assert [e["kind"] for e in body["expiries"]] == ["monthly"]
        assert c.get("/expiries", params={"underlying": "FINNIFTY"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_expiry_service, None)
