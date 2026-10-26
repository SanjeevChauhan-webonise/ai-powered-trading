from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import Cfg
from upstox.expiries import ExpiryError, ExpiryService, get_service

router = APIRouter(prefix="/expiries", tags=["expiries"])


def get_expiry_service(settings: Cfg) -> ExpiryService:
    return get_service(settings.storage_dir)


class ExpiryOut(BaseModel):
    date: date
    kind: Literal["weekly", "monthly"]
    days_to_expiry: int


class ExpiriesResponse(BaseModel):
    underlying: str
    lot_size: int | None
    source: str = "Upstox instruments file (exchange contract list)"
    fetched_at: datetime
    stale: bool
    expiries: list[ExpiryOut]


@router.get("", response_model=ExpiriesResponse, summary="Upcoming option expiries (live exchange contract list)")
def list_expiries(
    underlying: Literal["NIFTY", "BANKNIFTY"],
    service: Annotated[ExpiryService, Depends(get_expiry_service)],
    count: Annotated[int, Query(ge=1, le=30)] = 10,
) -> ExpiriesResponse:
    """Real expiry dates (holiday shifts included) and the lot size. `stale` means the last cached copy is shown
    because the download failed."""
    try:
        rows, table, stale = service.upcoming(underlying, count)
    except ExpiryError as e:
        raise HTTPException(502, str(e)) from e
    return ExpiriesResponse(
        underlying=underlying,
        lot_size=table.lot_sizes.get(underlying),
        fetched_at=table.fetched_at,
        stale=stale,
        expiries=[ExpiryOut(date=r.date, kind=r.kind, days_to_expiry=r.days) for r in rows],
    )
