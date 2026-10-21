import uuid

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import Db
from app.core.models import Strategy
from app.engine.templates import TEMPLATES
from app.schemas.api import StrategyCreate, StrategyOut, TemplateOut, ValidateRequest, ValidateResponse
from app.schemas.strategy import StrategySpec

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _out(row: Strategy) -> StrategyOut:
    return StrategyOut(id=row.id, name=row.name, spec=StrategySpec.model_validate(row.spec), created_at=row.created_at)


@router.get("/templates", response_model=list[TemplateOut], summary="Built-in strategy templates")
def list_templates() -> list[TemplateOut]:
    return [TemplateOut(id=k, name=s.name, description=s.description, spec=s) for k, s in TEMPLATES.items()]


@router.post("/validate", response_model=ValidateResponse, summary="Validate a strategy spec")
def validate_spec(req: ValidateRequest) -> ValidateResponse:
    try:
        spec = StrategySpec.model_validate(req.spec)
    except ValidationError as e:
        errors = [f"{'.'.join(str(p) for p in err['loc']) or 'spec'}: {err['msg']}" for err in e.errors()]
        return ValidateResponse(valid=False, errors=errors)
    return ValidateResponse(valid=True, spec=spec)


@router.post("", response_model=StrategyOut, summary="Save a strategy")
def create_strategy(req: StrategyCreate, db: Db) -> StrategyOut:
    row = Strategy(id=uuid.uuid4().hex, name=req.name or req.spec.name, spec=req.spec.model_dump(mode="json"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("", response_model=list[StrategyOut], summary="List saved strategies")
def list_strategies(db: Db) -> list[StrategyOut]:
    return [_out(r) for r in db.scalars(select(Strategy).order_by(Strategy.created_at.desc()))]


@router.get("/{strategy_id}", response_model=StrategyOut, summary="Get a saved strategy")
def get_strategy(strategy_id: str, db: Db) -> StrategyOut:
    row = db.get(Strategy, strategy_id)
    if row is None:
        raise HTTPException(404, "Strategy not found")
    return _out(row)
