from fastapi import APIRouter

from app.api.deps import Cfg
from app.llm.registry import ModelError, available_models, resolve_model
from app.schemas.llm import ModelsResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsResponse, summary="LLMs available from configured providers")
def list_models(settings: Cfg) -> ModelsResponse:
    try:
        resolve_model(settings)
        default_ok = True
    except ModelError:
        default_ok = False
    return ModelsResponse(
        default=settings.default_model, default_available=default_ok, models=available_models(settings)
    )
