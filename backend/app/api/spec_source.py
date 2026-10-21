from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.models import Strategy
from app.engine.templates import TEMPLATES
from app.schemas.strategy import StrategySpec


def resolve_spec(
    db: Session, *, spec: StrategySpec | None, template_id: str | None, strategy_id: str | None
) -> tuple[StrategySpec | None, str | None]:
    """Resolve whichever strategy source was given -> (spec, saved strategy id). (None, None) if none was given."""
    if spec is not None:
        return spec, None
    if template_id is not None:
        if template_id not in TEMPLATES:
            raise HTTPException(404, f"Unknown template '{template_id}'")
        return TEMPLATES[template_id], None
    if strategy_id is not None:
        row = db.get(Strategy, strategy_id)
        if row is None:
            raise HTTPException(404, "Strategy not found")
        return StrategySpec.model_validate(row.spec), row.id
    return None, None
