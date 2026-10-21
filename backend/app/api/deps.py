from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.agents.orchestrator import Pipeline
from app.core.config import Settings, get_settings
from app.core.db import get_db, get_session
from app.rag.embeddings import Embedder, get_embedder
from app.rag.store import VectorStore, get_store

Db = Annotated[Session, Depends(get_db)]
Cfg = Annotated[Settings, Depends(get_settings)]


def get_vector_store() -> VectorStore:
    return get_store()


def get_text_embedder() -> Embedder:
    return get_embedder()


Store = Annotated[VectorStore, Depends(get_vector_store)]
Emb = Annotated[Embedder, Depends(get_text_embedder)]


def get_session_factory(request: Request) -> Callable[[], Session]:
    """Sessions for background work. Tests set app.state.session_factory."""
    factory: Callable[[], Session] = getattr(request.app.state, "session_factory", get_session)
    return factory


SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]


def get_pipeline(settings: Cfg, factory: SessionFactory, store: Store, embedder: Emb) -> Pipeline:
    return Pipeline(settings, factory, store, embedder)


PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]
