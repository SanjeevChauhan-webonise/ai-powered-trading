from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    provider: str
    label: str


class ModelsResponse(BaseModel):
    default: str
    default_available: bool
    locked: bool = False  # the server ignores a requested model and always uses its default
    models: list[ModelInfo]
