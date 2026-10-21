from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.agents.orchestrator import Pipeline
from app.core.config import Settings, get_settings
from app.core.db import get_db, get_session
from app.core.models import AuthSession, User
from app.core.security import hash_token
from app.rag.embeddings import Embedder, get_embedder
from app.rag.store import VectorStore, get_store

Db = Annotated[Session, Depends(get_db)]
Cfg = Annotated[Settings, Depends(get_settings)]


def get_vector_store() -> VectorStore:
    return get_store()


def get_text_embedder() -> Embedder:
    return get_embedder()


def get_current_user(db: Db, authorization: Annotated[str | None, Header()] = None) -> User:
    """The user behind `Authorization: Bearer <token>`; 401 if the token is missing, unknown or expired."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() == "bearer" and token:
        session = db.get(AuthSession, hash_token(token.strip()))
        if session and session.expires_at > datetime.now(UTC).replace(tzinfo=None):
            user = db.get(User, session.user_id)
            if user:
                return user
    raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})


CurrentUser = Annotated[User, Depends(get_current_user)]

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
