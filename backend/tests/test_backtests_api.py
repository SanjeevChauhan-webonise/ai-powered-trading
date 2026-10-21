import pytest
from fastapi.testclient import TestClient

from app.engine.templates import TEMPLATES


@pytest.fixture
def dataset_id(client: TestClient) -> str:
    r = client.post("/datasets/synthetic", json={"trading_days": 6, "n_strikes": 4})
    assert r.status_code == 200, r.text
    return str(r.json()["id"])


def test_templates(client: TestClient) -> None:
    r = client.get("/strategies/templates")
    assert r.status_code == 200
    assert {t["id"] for t in r.json()} == set(TEMPLATES)
    assert r.json()[0]["spec"]["indicators"]


def test_validate(client: TestClient) -> None:
    spec = TEMPLATES["ema_crossover"].model_dump(mode="json")
    ok = client.post("/strategies/validate", json={"spec": spec}).json()
    assert ok["valid"] and ok["errors"] == [] and ok["spec"]["name"] == "EMA Crossover"
    bad = dict(spec, lots=0, entry_bullish={"left": {"indicator": "nope"}, "op": ">", "right": {"value": 1}})
    res = client.post("/strategies/validate", json={"spec": bad}).json()
    assert not res["valid"] and res["spec"] is None
    assert any(e.startswith("lots:") for e in res["errors"])


def test_save_and_list_strategy(client: TestClient) -> None:
    spec = TEMPLATES["rsi_reversal"].model_dump(mode="json")
    r = client.post("/strategies", json={"spec": spec, "name": "mine"})
    assert r.status_code == 200 and r.json()["name"] == "mine"
    sid = r.json()["id"]
    assert [s["id"] for s in client.get("/strategies").json()] == [sid]
    assert client.get(f"/strategies/{sid}").json()["spec"]["name"] == "RSI Reversal"
    assert client.get("/strategies/nope").status_code == 404
    assert client.post("/strategies", json={"spec": {"name": "x"}}).status_code == 422


def test_run_template_backtest_and_fetch(client: TestClient, dataset_id: str) -> None:
    r = client.post("/backtests", json={"dataset_id": dataset_id, "template_id": "ema_crossover"})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "completed" and run["error"] is None
    res = run["result"]
    assert res["metrics"]["num_trades"] == len(res["trades"]) == run["num_trades"] > 0
    assert run["total_pnl"] == pytest.approx(sum(t["net_pnl"] for t in res["trades"]), abs=0.05)
    assert res["equity_curve"] and res["metrics"]["daily_pnl"]
    assert run["spec"]["name"] == "EMA Crossover"

    got = client.get(f"/backtests/{run['id']}").json()
    assert got["result"] == res
    summaries = client.get("/backtests").json()
    assert [s["id"] for s in summaries] == [run["id"]] and "result" not in summaries[0]


def test_run_with_saved_strategy_inline_spec_and_range(client: TestClient, dataset_id: str) -> None:
    spec = TEMPLATES["ema_crossover"].model_dump(mode="json")
    sid = client.post("/strategies", json={"spec": spec}).json()["id"]
    a = client.post("/backtests", json={"dataset_id": dataset_id, "strategy_id": sid}).json()
    assert a["strategy_id"] == sid
    b = client.post(
        "/backtests", json={"dataset_id": dataset_id, "spec": spec, "start": "2024-01-03", "end": "2024-01-04"}
    ).json()
    assert b["strategy_id"] is None and b["result"]["start"] == "2024-01-03"
    assert all("2024-01-03" <= t["entry_time"][:10] <= "2024-01-04" for t in b["result"]["trades"])
    assert b["num_trades"] < a["num_trades"]


def test_backtest_errors(client: TestClient, dataset_id: str) -> None:
    def post(**kw):  # type: ignore[no-untyped-def]
        return client.post("/backtests", json=kw)

    assert post(dataset_id="nope", template_id="ema_crossover").status_code == 404
    assert post(dataset_id=dataset_id, template_id="zzz").status_code == 404
    assert post(dataset_id=dataset_id, strategy_id="zzz").status_code == 404
    assert post(dataset_id=dataset_id).status_code == 422  # no strategy source
    assert post(dataset_id=dataset_id, template_id="ema_crossover", strategy_id="x").status_code == 422
    assert (
        post(dataset_id=dataset_id, template_id="ema_crossover", start="2024-02-01", end="2024-01-01").status_code
        == 422
    )
    assert client.get("/backtests/nope").status_code == 404


def test_dataset_without_options_rejected(client: TestClient) -> None:
    import io
    import json

    from app.data.synthetic import SyntheticConfig, generate

    under, _ = generate(SyntheticConfig(trading_days=1))
    buf = io.BytesIO()
    under.to_parquet(buf, index=False)
    from app.schemas.data import ColumnMapping

    d = client.post(
        "/datasets/upload",
        files={"file": ("u.parquet", buf.getvalue())},
        data={
            "mapping": ColumnMapping.standard("underlying").model_dump_json(),
            "kind": "underlying",
            "underlying": "NIFTY",
        },
    ).json()
    r = client.post("/backtests", json={"dataset_id": d["id"], "template_id": "ema_crossover"})
    assert r.status_code == 400 and "option" in r.json()["detail"]
    assert json.loads(r.text)["detail"]


def test_engine_failure_is_recorded(client: TestClient, dataset_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import backtests

    def boom(*a, **k):  # type: ignore[no-untyped-def]
        raise ValueError("kaboom")

    monkeypatch.setattr(backtests, "run_backtest", boom)
    run = client.post("/backtests", json={"dataset_id": dataset_id, "template_id": "ema_crossover"}).json()
    assert run["status"] == "failed" and "kaboom" in run["error"] and run["result"] is None
