import os

from app.core.config import Settings

# Hermetic settings: tests must not depend on a developer's backend/.env or exported env vars.
Settings.model_config["env_file"] = None
for _name in Settings.model_fields:
    os.environ.pop(_name.upper(), None)
os.environ["RAG_AUTOINGEST"] = "false"  # tests never touch ChromaDB / the embedding model at startup

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.api.deps import get_text_embedder, get_vector_store  # noqa: E402
from app.core import models as core_models  # noqa: E402, F401
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
from app.data import models  # noqa: E402, F401
from app.main import app  # noqa: E402
from app.rag.store import InMemoryStore  # noqa: E402
from tests.rag_helpers import HashEmbedder  # noqa: E402


@pytest.fixture
def kb() -> tuple[InMemoryStore, HashEmbedder]:
    return InMemoryStore(), HashEmbedder()


def _setup(tmp_path: Path, kb: tuple[InMemoryStore, HashEmbedder], mock_llm: bool) -> None:
    # file-based sqlite: background pipeline tasks, SSE polling and requests each use their own connection
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)

    def _db() -> Iterator[Session]:
        with maker() as s:
            yield s

    store, embedder = kb
    app.state.session_factory = maker
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_vector_store] = lambda: store
    app.dependency_overrides[get_text_embedder] = lambda: embedder
    default_model = "mock:demo" if mock_llm else "openai:gpt-4o-mini"
    settings = Settings(storage_dir=str(tmp_path / "storage"), enable_mock_llm=mock_llm, default_model=default_model)
    app.dependency_overrides[get_settings] = lambda: settings


def _teardown() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "session_factory"):
        del app.state.session_factory


@pytest.fixture
def client(tmp_path: Path, kb: tuple[InMemoryStore, HashEmbedder]) -> Iterator[TestClient]:
    _setup(tmp_path, kb, mock_llm=False)
    yield TestClient(app)
    _teardown()


@pytest.fixture
def live_client(tmp_path: Path, kb: tuple[InMemoryStore, HashEmbedder]) -> Iterator[TestClient]:
    """Context-managed client (one persistent event loop, so background pipeline tasks keep running) + mock LLM."""
    _setup(tmp_path, kb, mock_llm=True)
    with TestClient(app) as c:
        yield c
    _teardown()
