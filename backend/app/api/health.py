import logging

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.schemas.health import HealthResponse, ServiceStatus

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


def _check_postgres() -> ServiceStatus:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "up"
    except Exception:
        log.warning("postgres health check failed")
        return "down"


def _check_chroma() -> ServiceStatus:
    s = get_settings()
    try:
        r = httpx.get(f"http://{s.chroma_host}:{s.chroma_port}/api/v2/heartbeat", timeout=2)
        return "up" if r.is_success else "down"
    except Exception:
        log.warning("chromadb health check failed")
        return "down"


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health() -> HealthResponse:
    services = {"postgres": _check_postgres(), "chromadb": _check_chroma()}
    ok = all(v == "up" for v in services.values())
    return HealthResponse(
        status="ok" if ok else "degraded",
        version=get_settings().app_version,
        services=services,
    )
