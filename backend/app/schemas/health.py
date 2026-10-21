from typing import Literal

from pydantic import BaseModel

ServiceStatus = Literal["up", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    services: dict[str, ServiceStatus]
