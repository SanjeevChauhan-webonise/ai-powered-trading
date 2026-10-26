from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core.models import AuthSession
from app.core.security import hash_password, hash_token, verify_password
from app.main import app
from tests.conftest import make_login
from tests.test_runs_api import IDEA, wait_done

PASSWORD = "Test@12345"


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    auth_api._fails.clear()


def anon() -> TestClient:
    return TestClient(app)  # no Authorization header


def register(c: TestClient, email: str = "new@example.com", **extra: Any) -> dict[str, Any]:
    r = c.post("/auth/register", json={"email": email, "name": "New User", "password": PASSWORD, **extra})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---- passwords ------------------------------------------------------------------------------
def test_password_hashing():
    h = hash_password(PASSWORD)
    assert h != hash_password(PASSWORD) and PASSWORD not in h  # salted
    assert verify_password(PASSWORD, h) and not verify_password("wrong-password", h)
    assert not verify_password(PASSWORD, "garbage") and not verify_password(PASSWORD, "md5$1$2$3$4$5")


# ---- register / login / me / logout ---------------------------------------------------------
def test_register_login_me_logout(client: TestClient):
    out = register(anon(), "Amit@Example.com", level="expert")
    assert out["user"]["email"] == "amit@example.com" and out["user"]["level"] == "expert"  # lower-cased
    c = anon()
    assert c.get("/auth/me", headers=bearer(out["token"])).json()["name"] == "New User"

    login = c.post("/auth/login", json={"email": "AMIT@example.com", "password": PASSWORD})
    assert login.status_code == 200 and login.json()["token"] != out["token"]
    h = bearer(login.json()["token"])
    assert c.post("/auth/logout", headers=h).status_code == 204
    assert c.get("/auth/me", headers=h).status_code == 401  # the logged-out token is dead
    assert c.get("/auth/me", headers=bearer(out["token"])).status_code == 200  # other logins are untouched


def test_default_level_is_beginner_and_validation(client: TestClient):
    assert register(anon())["user"]["level"] == "beginner"
    c = anon()
    base = {"email": "x@example.com", "name": "X", "password": PASSWORD}
    assert c.post("/auth/register", json={**base, "password": "short"}).status_code == 422
    assert c.post("/auth/register", json={**base, "email": "not-an-email"}).status_code == 422
    assert c.post("/auth/register", json={**base, "level": "guru"}).status_code == 422
    assert c.post("/auth/register", json={**base, "email": "other@example.com"}).status_code == 201
    assert c.post("/auth/register", json={**base, "email": "OTHER@example.com"}).status_code == 409


def test_login_errors_are_generic_and_rate_limited(client: TestClient):
    register(anon())
    c = anon()
    bad = c.post("/auth/login", json={"email": "new@example.com", "password": "wrong-password"})
    unknown = c.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()
    for _ in range(auth_api.MAX_FAILS):
        c.post("/auth/login", json={"email": "new@example.com", "password": "wrong-password"})
    locked = c.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert locked.status_code == 429  # even the right password is refused while locked


def test_registration_can_be_disabled(client: TestClient):
    from app.core.config import get_settings

    s = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: s.model_copy(update={"allow_registration": False})
    r = anon().post("/auth/register", json={"email": "a@example.com", "name": "A", "password": PASSWORD})
    assert r.status_code == 403


def test_update_profile_and_change_password(client: TestClient):
    out = register(anon())
    c = anon()
    h = bearer(out["token"])
    other = bearer(c.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD}).json()["token"])
    assert c.patch("/auth/me", headers=h, json={"level": "advanced", "name": "Renamed"}).json()["level"] == "advanced"
    assert (
        c.post(
            "/auth/change-password", headers=h, json={"current_password": "nope", "new_password": "Another@123"}
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "Another@123"}
        ).status_code
        == 204
    )
    assert c.get("/auth/me", headers=h).status_code == 200  # this login stays
    assert c.get("/auth/me", headers=other).status_code == 401  # the other login was ended
    assert c.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD}).status_code == 401
    assert c.post("/auth/login", json={"email": "new@example.com", "password": "Another@123"}).status_code == 200


# ---- access control -------------------------------------------------------------------------
PROTECTED = [
    ("GET", "/datasets"), ("GET", "/strategies"), ("GET", "/backtests"), ("GET", "/runs"), ("GET", "/models"),
    ("GET", "/knowledge/documents"), ("POST", "/runs/parse"),
    ("POST", "/runs/ask"), ("GET", "/auth/me"),
]  # fmt: skip


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_routes_need_a_login(client: TestClient, method: str, path: str):
    assert anon().request(method, path, json={}).status_code == 401


def test_open_routes_and_bad_tokens(client: TestClient):
    c = anon()
    assert c.get("/health").status_code in (200, 503) and c.get("/docs").status_code == 200
    for header in ({"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}):
        assert c.get("/auth/me", headers=header).status_code == 401


def test_expired_session_is_rejected(client: TestClient):
    out = register(anon())
    maker = app.state.session_factory
    with maker() as s:
        sess = s.get(AuthSession, hash_token(out["token"]))
        assert sess is not None
        sess.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        s.commit()
    assert anon().get("/auth/me", headers=bearer(out["token"])).status_code == 401


# ---- per-user data ---------------------------------------------------------------------------
def test_strategies_and_backtests_are_private(client: TestClient):
    ds = client.post("/datasets/synthetic", json={"trading_days": 3, "n_strikes": 2}).json()["id"]
    spec = client.get("/strategies/templates").json()[0]["spec"]
    sid = client.post("/strategies", json={"spec": spec}).json()["id"]
    bid = client.post("/backtests", json={"dataset_id": ds, "template_id": "ema_crossover"}).json()["id"]
    assert [x["id"] for x in client.get("/strategies").json()] == [sid]

    bob = TestClient(app)
    bob.headers.update(make_login(app.state.session_factory, "bob@example.com", "Bob"))
    assert bob.get("/strategies").json() == [] and bob.get("/backtests").json() == []
    assert bob.get(f"/strategies/{sid}").status_code == 404
    assert bob.get(f"/backtests/{bid}").status_code == 404
    r = bob.post("/backtests", json={"dataset_id": ds, "strategy_id": sid})  # cannot run on someone else's strategy
    assert r.status_code == 404
    assert bob.get(f"/datasets/{ds}").status_code == 200  # market data is shared
    assert client.get(f"/backtests/{bid}").status_code == 200


def test_runs_are_private_and_carry_the_owner(live_client: TestClient):
    ds = live_client.post("/datasets/synthetic", json={"trading_days": 6, "n_strikes": 4}).json()["id"]
    rid = live_client.post("/runs", json={"dataset_id": ds, "idea": IDEA}).json()["id"]
    run = wait_done(live_client, rid)
    assert run["status"] == "completed"
    bt = live_client.get(f"/backtests/{run['backtest_run_id']}")
    assert bt.status_code == 200  # the pipeline's backtest belongs to the same user

    bob = TestClient(app)
    bob.headers.update(make_login(app.state.session_factory, "bob@example.com", "Bob"))
    assert bob.get("/runs").json() == []
    assert bob.get(f"/runs/{rid}").status_code == 404
    assert bob.get(f"/runs/{rid}/stream").status_code == 404
    assert bob.get(f"/backtests/{run['backtest_run_id']}").status_code == 404
    assert [r["id"] for r in live_client.get("/runs").json()] == [rid]


# ---- experience levels ----------------------------------------------------------------------
def test_beginner_gets_guardrails_and_a_risk_note(live_client: TestClient):
    live_client.patch("/auth/me", json={"level": "beginner"})
    ds = live_client.post("/datasets/synthetic", json={"trading_days": 6, "n_strikes": 4}).json()["id"]
    body = {"dataset_id": ds, "template_id": "ema_crossover", "capital": 100000, "max_loss": 5000}
    run = wait_done(live_client, live_client.post("/runs", json=body).json()["id"])
    assert run["status"] == "completed", run["error"]
    plan = next(s for s in run["steps"] if s["name"] == "risk")["output"]["trade_plan"]
    assert plan["level"] == "beginner"
    assert any("5.0% of capital" in n and "beginner" in n for n in plan["notes"])  # 5% is above the 2% suggestion
    assert any("at most 3 trades" in n for n in plan["notes"])
    bt = live_client.get(f"/backtests/{run['backtest_run_id']}").json()
    assert bt["spec"]["risk"]["max_trades_per_day"] == 3


def test_expert_gets_no_beginner_guardrails(live_client: TestClient):
    live_client.patch("/auth/me", json={"level": "expert"})
    ds = live_client.post("/datasets/synthetic", json={"trading_days": 6, "n_strikes": 4}).json()["id"]
    body = {"dataset_id": ds, "template_id": "ema_crossover", "capital": 100000, "max_loss": 5000}
    run = wait_done(live_client, live_client.post("/runs", json=body).json()["id"])
    plan = next(s for s in run["steps"] if s["name"] == "risk")["output"]["trade_plan"]
    assert plan["level"] == "expert" and not any("beginner" in n.lower() for n in plan["notes"])
    assert live_client.get(f"/backtests/{run['backtest_run_id']}").json()["spec"]["risk"]["max_trades_per_day"] is None
