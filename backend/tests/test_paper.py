import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.models import PipelineRun
from app.main import app
from tests.conftest import make_login

LOT = 75


@pytest.fixture
def ds(client: TestClient) -> str:
    r = client.post("/datasets/synthetic", json={"trading_days": 6, "n_strikes": 4, "lot_size": LOT})
    assert r.status_code == 200, r.text
    return str(r.json()["id"])


def started(client: TestClient, ds: str) -> dict[str, Any]:
    r = client.post("/paper/clock/start", json={"dataset_id": ds})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def atm_order(client: TestClient, *, option_type: str = "CE", lots: int = 1, **extra: Any) -> dict[str, Any]:
    expiry = client.get("/paper/expiries").json()["expiries"][0]
    chain = client.get("/paper/chain", params={"expiry": expiry}).json()
    spot = chain["spot"]
    strike = min((r["strike"] for r in chain["rows"]), key=lambda k: abs(k - spot))
    r = client.post(
        "/paper/orders", json={"expiry": expiry, "strike": strike, "option_type": option_type, "lots": lots, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def assert_cash_matches_pnl(client: TestClient) -> None:
    a = client.get("/paper/account").json()
    open_cost = sum(p["avg_price"] * p["qty"] for p in client.get("/paper/positions").json())
    assert abs(a["cash"] + open_cost - (a["starting_balance"] + a["realized_pnl"])) < 0.05


def plan_run(user_id: str, dataset_id: str, **plan: Any) -> str:
    base = {
        "expiry_date": None, "strike": {"mode": "atm", "offset": 0, "premium": None}, "lots": 2,
        "stop_loss_pct": 20.0, "target_pct": 40.0, "square_off": "15:15",
        "bullish_signal_action": "buy CE", "bearish_signal_action": "sell PE",
    }  # fmt: skip
    steps = [{"name": "risk", "status": "completed", "output": {"trade_plan": {**base, **plan}}}]
    with app.state.session_factory() as s:
        run = PipelineRun(
            id=uuid.uuid4().hex, dataset_id=dataset_id, user_id=user_id, status="completed", request={}, steps=steps,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )  # fmt: skip
        s.add(run)
        s.commit()
        return run.id


def test_new_account_and_clock(client: TestClient, ds: str):
    a = client.get("/paper/account").json()
    assert a["starting_balance"] == a["cash"] == a["equity"] == 500_000 and a["clock_time"] is None
    r = client.post("/paper/orders", json={"expiry": "2024-01-04", "strike": 22000, "option_type": "CE", "lots": 1})
    assert r.status_code == 400 and "market clock" in r.json()["detail"]
    a = started(client, ds)
    assert a["clock_time"].startswith("2024-01-04T09:15") and a["lot_size"] == LOT and a["underlying"] == "NIFTY"
    assert client.post("/paper/clock/start", json={"dataset_id": "nope"}).status_code == 400


def test_buy_creates_position_and_moves_cash(client: TestClient, ds: str):
    started(client, ds)
    order = atm_order(client, lots=2)
    cost = order["price"] * order["qty"]
    assert order["qty"] == 2 * LOT and order["side"] == "buy" and order["status"] == "filled"
    a = client.get("/paper/account").json()
    assert abs(a["cash"] - (500_000 - cost)) < 0.02 and a["open_positions"] == 1
    assert abs(a["equity"] - 500_000) < 0.02  # marked at the price it was bought at
    p = client.get("/paper/positions").json()[0]
    assert p["lots"] == 2 and p["avg_price"] == order["price"] and p["unrealized_pnl"] == 0
    assert client.get("/paper/orders").json()[0]["id"] == order["id"]


def test_adding_to_a_position_averages_the_price(client: TestClient, ds: str):
    started(client, ds)
    atm_order(client, lots=1)
    client.post("/paper/clock/advance", json={"candles": 40})
    atm_order(client, lots=1)
    pos = client.get("/paper/positions").json()
    assert len(pos) == 1 and pos[0]["lots"] == 2
    orders = client.get("/paper/orders").json()
    expected = (orders[1]["price"] + orders[0]["price"]) / 2
    assert abs(pos[0]["avg_price"] - expected) < 0.02


def test_insufficient_cash_is_rejected_and_recorded(client: TestClient, ds: str):
    started(client, ds)
    client.post("/paper/account/reset", json={"starting_balance": 100})
    started(client, ds)
    expiry = client.get("/paper/expiries").json()["expiries"][0]
    chain = client.get("/paper/chain", params={"expiry": expiry}).json()
    r = client.post("/paper/orders", json={"expiry": expiry, "strike": chain["rows"][0]["strike"], "option_type": "CE"})
    assert r.status_code == 400 and "Insufficient cash" in r.json()["detail"]
    orders = client.get("/paper/orders").json()
    assert orders[0]["status"] == "rejected" and client.get("/paper/positions").json() == []
    assert client.get("/paper/account").json()["cash"] == 100


def test_close_realises_pnl_with_costs_and_cash_matches(client: TestClient, ds: str):
    started(client, ds)
    atm_order(client, lots=2)
    client.post("/paper/clock/advance", json={"candles": 60})
    pos = client.get("/paper/positions").json()[0]
    t = client.post(f"/paper/positions/{pos['id']}/close", json={}).json()
    assert t["qty"] == 2 * LOT and t["exit_reason"] == "manual"
    assert abs(t["gross_pnl"] - (t["exit_price"] - t["entry_price"]) * t["qty"]) < 0.02
    expected_costs = 40 + 0.05 / 100 * (t["entry_price"] + t["exit_price"]) * t["qty"]
    assert abs(t["costs"] - expected_costs) < 0.02 and abs(t["net_pnl"] - (t["gross_pnl"] - t["costs"])) < 0.02
    assert client.get("/paper/positions").json() == []
    assert client.get("/paper/trades").json()[0]["id"] == t["id"]
    assert_cash_matches_pnl(client)
    a = client.get("/paper/account").json()
    assert abs(a["realized_pnl"] - t["net_pnl"]) < 0.02 and a["open_positions"] == 0


def test_partial_close_and_overselling(client: TestClient, ds: str):
    started(client, ds)
    atm_order(client, lots=2)
    pid = client.get("/paper/positions").json()[0]["id"]
    assert client.post(f"/paper/positions/{pid}/close", json={"lots": 3}).status_code == 400  # you hold 2
    t = client.post(f"/paper/positions/{pid}/close", json={"lots": 1}).json()
    assert t["qty"] == LOT
    left = client.get("/paper/positions").json()
    assert len(left) == 1 and left[0]["lots"] == 1
    assert_cash_matches_pnl(client)


def test_stop_or_target_exits_run_as_the_clock_advances(client: TestClient, ds: str):
    started(client, ds)
    atm_order(client, stop_pct=0.01, target_pct=0.01)  # any move of the premium triggers one of them
    r = client.post("/paper/clock/advance", json={"candles": 50}).json()
    assert [e["exit_reason"] for e in r["exits"]] and r["exits"][0]["exit_reason"] in ("stop", "target")
    assert r["account"]["open_positions"] == 0
    assert any(o["source"] == "auto" and o["side"] == "sell" for o in client.get("/paper/orders").json())
    assert_cash_matches_pnl(client)


def test_positions_are_closed_at_expiry(client: TestClient, ds: str):
    started(client, ds)  # the clock starts on 4 Jan, which is the first expiry
    atm_order(client)
    r = client.post("/paper/clock/advance", json={"candles": 2000}).json()
    assert r["at_end"] and [e["exit_reason"] for e in r["exits"]] == ["expiry"]
    assert_cash_matches_pnl(client)


def test_advance_beyond_the_data_stops_at_the_end(client: TestClient, ds: str):
    started(client, ds)
    r = client.post("/paper/clock/advance", json={"candles": 2000}).json()
    assert r["at_end"] and r["account"]["clock_time"] == r["account"]["clock_end"]
    assert client.post("/paper/clock/advance", json={"candles": 5}).json()["at_end"]


def test_clock_cannot_restart_with_open_positions_but_reset_works(client: TestClient, ds: str):
    started(client, ds)
    atm_order(client)
    assert client.post("/paper/clock/start", json={"dataset_id": ds}).status_code == 409
    a = client.post("/paper/account/reset", json={"starting_balance": 250_000}).json()
    assert a["cash"] == a["starting_balance"] == 250_000 and a["clock_time"] is None
    assert client.get("/paper/positions").json() == [] and client.get("/paper/orders").json() == []


def test_paper_trade_from_an_ai_plan(client: TestClient, ds: str):
    uid = client.get("/auth/me").json()["id"]
    rid = plan_run(uid, ds)
    out = client.post("/paper/from-plan", json={"run_id": rid, "option_type": "CE"})
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["order"]["source"] == "plan" and body["order"]["qty"] == 2 * LOT
    assert any("clock was started" in n for n in body["notes"])  # no clock yet: started on the plan's dataset
    pos = client.get("/paper/positions").json()[0]
    assert (
        pos["stop_pct"] == 20.0 and pos["target_pct"] == 40.0 and pos["square_off"] == "15:15" and pos["run_id"] == rid
    )

    assert client.post("/paper/from-plan", json={"run_id": rid, "option_type": "PE"}).status_code == 409  # "sell PE"
    empty = uuid.uuid4().hex
    with app.state.session_factory() as s:
        s.add(PipelineRun(id=empty, dataset_id=ds, user_id=uid, status="running", request={}, steps=[]))
        s.commit()
    assert client.post("/paper/from-plan", json={"run_id": empty, "option_type": "CE"}).status_code == 409

    r = client.post("/paper/clock/advance", json={"candles": 400}).json()  # about one session at 1-minute candles
    assert r["exits"] and r["exits"][0]["exit_reason"] in ("stop", "target", "squareoff")
    assert_cash_matches_pnl(client)


def test_plan_strike_offset_moves_away_from_the_money(client: TestClient, ds: str):
    uid = client.get("/auth/me").json()["id"]
    atm = client.post("/paper/from-plan", json={"run_id": plan_run(uid, ds, lots=1), "option_type": "CE"}).json()
    otm = client.post(
        "/paper/from-plan",
        json={
            "run_id": plan_run(uid, ds, lots=1, strike={"mode": "offset", "offset": 2, "premium": None}),
            "option_type": "CE",
        },
    ).json()
    assert otm["order"]["strike"] == atm["order"]["strike"] + 100  # two 50-point steps up


def test_accounts_and_positions_are_private(client: TestClient, ds: str):
    started(client, ds)
    atm_order(client)
    pid = client.get("/paper/positions").json()[0]["id"]
    bob = TestClient(app)
    bob.headers.update(make_login(app.state.session_factory, "bob@example.com", "Bob"))
    a = bob.get("/paper/account").json()
    assert a["cash"] == 500_000 and a["open_positions"] == 0 and a["clock_time"] is None
    assert bob.get("/paper/positions").json() == [] and bob.get("/paper/trades").json() == []
    assert bob.post(f"/paper/positions/{pid}/close", json={}).status_code == 400
    uid = client.get("/auth/me").json()["id"]
    assert bob.post("/paper/from-plan", json={"run_id": plan_run(uid, ds), "option_type": "CE"}).status_code == 404


def test_paper_routes_need_a_login(client: TestClient):
    assert TestClient(app).get("/paper/account").status_code == 401


def test_expiries_not_yet_listed_are_not_offered(client: TestClient):
    from app.core.config import get_settings
    from app.data import service as data_service
    from app.data.synthetic import SyntheticConfig, generate
    from app.schemas.data import ColumnMapping

    under, opts = generate(SyntheticConfig(trading_days=4, n_strikes=2))
    day2 = sorted(set(opts["timestamp"].dt.date))[1]
    late = max(opts["expiry"])  # pretend the furthest contract is only listed from day 2
    opts = opts[~((opts["expiry"] == late) & (opts["timestamp"].dt.date < day2))]
    settings = app.dependency_overrides[get_settings]()
    with app.state.session_factory() as s:
        row = data_service.ingest(
            s,
            settings,
            under,
            kind="underlying",
            mapping=ColumnMapping.standard("underlying"),
            underlying="NIFTY",
            lot_size=LOT,
        )
        row = data_service.ingest(
            s,
            settings,
            opts,
            kind="options",
            mapping=ColumnMapping.standard("options"),
            underlying="NIFTY",
            dataset_id=row.id,
        )
        ds_id = row.id
    assert client.post("/paper/clock/start", json={"dataset_id": ds_id, "at": "2024-01-01T09:15:00"}).status_code == 200
    day1 = client.get("/paper/expiries").json()["expiries"]
    assert late.date().isoformat() not in day1 and len(day1) >= 2
    r = client.post(
        "/paper/orders", json={"expiry": late.date().isoformat(), "strike": 22000, "option_type": "CE", "lots": 1}
    )
    assert r.status_code == 400 and "not an available expiry" in r.json()["detail"]
    client.post("/paper/clock/advance", json={"candles": 400})  # into day 2: now it is listed
    assert late.date().isoformat() in client.get("/paper/expiries").json()["expiries"]


def two_days_of_trades(client: TestClient, ds: str) -> list[dict[str, Any]]:
    """One CE closed on 4 Jan and one PE closed on 5 Jan (1-minute candles: 375 a day)."""
    started(client, ds)
    out = []
    for option_type, candles in (("CE", 60), ("PE", 30)):
        atm_order(client, option_type=option_type)
        client.post("/paper/clock/advance", json={"candles": candles})
        pid = client.get("/paper/positions").json()[0]["id"]
        out.append(client.post(f"/paper/positions/{pid}/close", json={}).json())
        if option_type == "CE":
            client.post("/paper/clock/advance", json={"candles": 375})  # into the next trading day
    return out


def test_pnl_by_date_and_range(client: TestClient, ds: str):
    t1, t2 = two_days_of_trades(client, ds)
    assert t1["exit_time"][:10] == "2024-01-04" and t2["exit_time"][:10] == "2024-01-05"

    allp = client.get("/paper/pnl").json()
    s = allp["summary"]
    assert s["trades"] == 2 and abs(s["net_pnl"] - (t1["net_pnl"] + t2["net_pnl"])) < 0.02
    assert abs(s["gross_pnl"] - (t1["gross_pnl"] + t2["gross_pnl"])) < 0.02
    assert abs(s["net_pnl"] - (s["gross_pnl"] - s["costs"])) < 0.02
    assert allp["available_from"] == "2024-01-04" and allp["available_to"] == "2024-01-05"
    assert [d["date"] for d in allp["daily"]] == ["2024-01-04", "2024-01-05"]
    assert abs(allp["daily"][-1]["cumulative"] - s["net_pnl"]) < 0.02
    assert {g["key"] for g in allp["by_option_type"]} == {"CE", "PE"} and allp["by_exit_reason"][0]["key"] == "manual"
    assert s["wins"] + s["losses"] <= 2 and s["max_drawdown"] >= 0

    one = client.get("/paper/pnl", params={"date_from": "2024-01-04", "date_to": "2024-01-04"}).json()
    assert one["summary"]["trades"] == 1 and abs(one["summary"]["net_pnl"] - t1["net_pnl"]) < 0.02
    assert one["available_from"] == "2024-01-04" and one["available_to"] == "2024-01-05"  # bounds ignore the filter
    tail = client.get("/paper/pnl", params={"date_from": "2024-01-05"}).json()
    assert tail["summary"]["trades"] == 1 and tail["daily"][0]["cumulative"] == tail["daily"][0]["net_pnl"]
    head = client.get("/paper/pnl", params={"date_to": "2024-01-04"}).json()
    assert head["summary"]["trades"] == 1


def test_pnl_empty_range_and_bad_range(client: TestClient, ds: str):
    two_days_of_trades(client, ds)
    empty = client.get("/paper/pnl", params={"date_from": "2030-01-01", "date_to": "2030-01-31"}).json()
    assert empty["summary"]["trades"] == 0 and empty["summary"]["win_rate_pct"] is None and empty["daily"] == []
    assert empty["summary"]["profit_factor"] is None and empty["summary"]["best_trade"] is None
    r = client.get("/paper/pnl", params={"date_from": "2024-01-05", "date_to": "2024-01-04"})
    assert r.status_code == 400
    assert client.get("/paper/pnl", params={"date_from": "nonsense"}).status_code == 422


def test_trades_can_be_filtered_by_date_and_pnl_is_private(client: TestClient, ds: str):
    two_days_of_trades(client, ds)
    jan4 = client.get("/paper/trades", params={"date_from": "2024-01-04", "date_to": "2024-01-04"}).json()
    jan5 = client.get("/paper/trades", params={"date_from": "2024-01-05"}).json()
    assert len(jan4) == 1 and jan4[0]["option_type"] == "CE" and len(jan5) == 1 and jan5[0]["option_type"] == "PE"
    assert len(client.get("/paper/trades").json()) == 2
    bob = TestClient(app)
    bob.headers.update(make_login(app.state.session_factory, "bob@example.com", "Bob"))
    b = bob.get("/paper/pnl").json()
    assert b["summary"]["trades"] == 0 and b["available_from"] is None and bob.get("/paper/trades").json() == []
