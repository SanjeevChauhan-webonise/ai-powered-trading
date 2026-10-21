from fastapi.testclient import TestClient

from app.api import health
from app.main import app

client = TestClient(app)


def test_health_all_up(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(health, "_check_postgres", lambda: "up")
    monkeypatch.setattr(health, "_check_chroma", lambda: "up")
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_degraded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(health, "_check_postgres", lambda: "down")
    monkeypatch.setattr(health, "_check_chroma", lambda: "up")
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["services"]["postgres"] == "down"
