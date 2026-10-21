import logging
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Local ONNX embeddings (default: all-MiniLM-L6-v2). No API key; model is downloaded once to the cache dir."""

    def __init__(self, model: str, cache_dir: str) -> None:
        self.name = model
        self._model_name, self._cache_dir = model, cache_dir
        self._model: object | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            log.info("loading embedding model %s", self._model_name)
            self._model = TextEmbedding(model_name=self._model_name, cache_dir=self._cache_dir)
        return [v.tolist() for v in self._model.embed(texts)]  # type: ignore[attr-defined]


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "fastembed":
        return FastEmbedEmbedder(settings.embedding_model, settings.model_cache_dir)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER '{settings.embedding_provider}' (supported: fastembed)")


@lru_cache
def get_embedder() -> Embedder:
    return build_embedder(get_settings())
