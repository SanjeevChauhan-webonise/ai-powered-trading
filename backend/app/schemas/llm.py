from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    provider: str
    label: str


class ModelsResponse(BaseModel):
    default: str
    default_available: bool
    models: list[ModelInfo]
