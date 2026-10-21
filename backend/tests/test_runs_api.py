import io
import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.data.synthetic import SyntheticConfig, generate
from app.rag import ingest
from app.schemas.data import ColumnMapping

IDEA = "Buy CE when the 9 EMA crosses above the 21 EMA on 5 minute candles"


@pytest.fixture(autouse=True)
def _populated_kb(kb: Any, tmp_path: Path) -> None:
    ingest.ingest_all(kb[0], kb[1], Settings(storage_dir=str(tmp_path / "storage")))


@pytest.fixture
def dataset_id(live_client: TestClient) -> str:
    r = live_client.post("/datasets/synthetic", json={"trading_days": 6, "n_strikes": 4})
    assert r.status_code == 200, r.text
    return str(r.json()["id"])


def wait_done(c: TestClient, run_id: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = c.get(f"/runs/{run_id}").json()
        if run["status"] in ("completed", "failed"):
            return run  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def read_sse(c: TestClient, run_id: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    with c.stream("GET", f"/runs/{run_id}/stream") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name:
                events.append((name, json.loads(line[6:])))
    return events


def test_run_to_completion_and_links_to_backtest(live_client: TestClient, dataset_id: str) -> None:
    r = live_client.post("/runs", json={"dataset_id": dataset_id, "idea": IDEA})
    assert r.status_code == 202
    summary = r.json()
    assert summary["status"] in ("queued", "running") and summary["idea"] == IDEA and summary["backtest_run_id"] is None
    run = wait_done(live_client, summary["id"])
    assert run["status"] == "completed" and run["error"] is None
    assert [s["status"] for s in run["steps"]] == ["completed"] * 4
    assert run["request"]["idea"] == IDEA
    bt = live_client.get(f"/backtests/{run['backtest_run_id']}").json()  # the normal results API works for AI runs
    assert bt["status"] == "completed" and bt["result"]["metrics"]["num_trades"] > 0
    assert bt["spec"]["name"] == "EMA Crossover"
    assert [x["id"] for x in live_client.get("/runs").json()] == [run["id"]]


def test_template_run_skips_strategy(live_client: TestClient, dataset_id: str) -> None:
    rid = live_client.post("/runs", json={"dataset_id": dataset_id, "template_id": "rsi_reversal"}).json()["id"]
    run = wait_done(live_client, rid)
    assert run["status"] == "completed" and run["steps"][1]["status"] == "skipped"


def test_sse_event_sequence_and_late_subscriber(live_client: TestClient, dataset_id: str) -> None:
    rid = live_client.post("/runs", json={"dataset_id": dataset_id, "idea": IDEA}).json()["id"]
    live = read_sse(live_client, rid)  # connected while the run is in flight (or just after)
    names = [e for e, _ in live]
    assert names[-1] == "done" and names.count("done") == 1 and "run" in names
    completed = [d["name"] for e, d in live if e == "step" and d["status"] == "completed"]
    assert completed == ["research", "strategy", "backtest", "risk"]  # in pipeline order, each exactly once
    risk = next(d for e, d in live if e == "step" and d["name"] == "risk" and d["status"] == "completed")
    assert risk["output"]["review"]["summary"] and risk["usage"]["requests"] >= 1
    assert live[-1][1]["status"] == "completed" and live[-1][1]["backtest_run_id"]

    # a client that connects after the run finished still gets the full history, then done
    late = read_sse(live_client, rid)
    assert [d["name"] for e, d in late if e == "step"] == ["research", "strategy", "backtest", "risk"]
    assert [e for e, _ in late][-2:] == ["run", "done"]


def test_sse_failed_run(live_client: TestClient, dataset_id: str, tmp_path: Path) -> None:
    shutil.rmtree(tmp_path / "storage" / dataset_id)  # the dataset's Parquet files vanish after validation
    rid = live_client.post("/runs", json={"dataset_id": dataset_id, "template_id": "ema_crossover"}).json()["id"]
    events = read_sse(live_client, rid)
    assert (
        events[-1][0] == "done"
        and events[-1][1]["status"] == "failed"
        and "FileNotFoundError" in events[-1][1]["error"]
    )
    run = live_client.get(f"/runs/{rid}").json()
    assert run["status"] == "failed" and [s["status"] for s in run["steps"]] == ["skipped"] * 4
    assert run["backtest_run_id"] is None


def test_validation_and_errors(live_client: TestClient, dataset_id: str) -> None:
    post = live_client.post
    assert post("/runs", json={"dataset_id": "nope", "idea": IDEA}).status_code == 404
    assert post("/runs", json={"dataset_id": dataset_id}).status_code == 422  # no idea, no strategy source
    assert post("/runs", json={"dataset_id": dataset_id, "idea": "  "}).status_code == 422
    assert post("/runs", json={"dataset_id": dataset_id, "idea": "x" * 2001}).status_code == 422
    assert (
        post("/runs", json={"dataset_id": dataset_id, "template_id": "ema_crossover", "strategy_id": "x"}).status_code
        == 422
    )
    assert (
        post(
            "/runs", json={"dataset_id": dataset_id, "idea": IDEA, "start": "2024-02-01", "end": "2024-01-01"}
        ).status_code
        == 422
    )
    assert post("/runs", json={"dataset_id": dataset_id, "template_id": "zzz"}).status_code == 404
    assert post("/runs", json={"dataset_id": dataset_id, "strategy_id": "zzz"}).status_code == 404
    bad_model = post("/runs", json={"dataset_id": dataset_id, "idea": IDEA, "model": "openai:gpt-4o"})
    assert bad_model.status_code == 400 and "not configured" in bad_model.json()["detail"]
    assert post("/runs", json={"dataset_id": dataset_id, "idea": IDEA, "model": "gpt-4o"}).status_code == 400
    assert live_client.get("/runs/nope").status_code == 404
    assert live_client.get("/runs/nope/stream").status_code == 404
    assert live_client.get("/runs").json() == []  # nothing was created by the rejected requests


def test_no_provider_configured_is_rejected_up_front(client: TestClient) -> None:
    ds = client.post("/datasets/synthetic", json={"trading_days": 2, "n_strikes": 2}).json()["id"]
    r = client.post("/runs", json={"dataset_id": ds, "template_id": "ema_crossover"})
    assert r.status_code == 400 and "not configured" in r.json()["detail"]
    assert client.get("/runs").json() == []


def test_dataset_without_options_rejected(live_client: TestClient) -> None:
    under, _ = generate(SyntheticConfig(trading_days=1))
    buf = io.BytesIO()
    under.to_parquet(buf, index=False)
    d = live_client.post(
        "/datasets/upload",
        files={"file": ("u.parquet", buf.getvalue())},
        data={
            "mapping": ColumnMapping.standard("underlying").model_dump_json(),
            "kind": "underlying",
            "underlying": "NIFTY",
        },
    ).json()
    r = live_client.post("/runs", json={"dataset_id": d["id"], "template_id": "ema_crossover"})
    assert r.status_code == 400 and "option" in r.json()["detail"]


def test_models_lists_mock_when_enabled(live_client: TestClient) -> None:
    body = live_client.get("/models").json()
    assert "mock:demo" in {m["id"] for m in body["models"]} and body["default_available"] is True


def test_models_hides_mock_by_default(client: TestClient) -> None:
    assert "mock:demo" not in {m["id"] for m in client.get("/models").json()["models"]}
