import os

from app.core.config import Settings

# Hermetic settings: tests must not depend on a developer's backend/.env or exported env vars.
Settings.model_config["env_file"] = None
for _name in Settings.model_fields:
    os.environ.pop(_name.upper(), None)
os.environ["RAG_BUILTIN_DOCS"] = "true"  # tests exercise the built-in notes
os.environ["RAG_AUTOINGEST"] = "false"  # tests never touch ChromaDB / the embedding model at startup

import uuid  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.api.deps import get_text_embedder, get_vector_store  # noqa: E402
from app.core import models as core_models  # noqa: E402, F401
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
from app.core.models import AuthSession, User  # noqa: E402
from app.core.security import hash_token, new_token  # noqa: E402
from app.data import models  # noqa: E402, F401
from app.main import app  # noqa: E402
from app.rag.store import InMemoryStore  # noqa: E402
from tests.rag_helpers import HashEmbedder  # noqa: E402


@pytest.fixture
def kb() -> tuple[InMemoryStore, HashEmbedder]:
    return InMemoryStore(), HashEmbedder()


def make_login(
    maker: Callable[[], Session], email: str = "tester@example.com", name: str = "Tester", level: str = "advanced"
) -> dict[str, str]:
    """Insert a user and a live session straight into the test DB; returns the Authorization header for them."""
    token = new_token()
    with maker() as s:
        uid = uuid.uuid4().hex
        s.add(User(id=uid, email=email, name=name, level=level, password_hash="not-a-real-hash"))
        s.add(
            AuthSession(
                token_hash=hash_token(token),
                user_id=uid,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
            )
        )
        s.commit()
    return {"Authorization": f"Bearer {token}"}


def _setup(tmp_path: Path, kb: tuple[InMemoryStore, HashEmbedder], mock_llm: bool) -> dict[str, str]:
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
    return make_login(maker)


def _teardown() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "session_factory"):
        del app.state.session_factory


@pytest.fixture
def client(tmp_path: Path, kb: tuple[InMemoryStore, HashEmbedder]) -> Iterator[TestClient]:
    auth = _setup(tmp_path, kb, mock_llm=False)
    c = TestClient(app)
    c.headers.update(auth)  # every test client is logged in as "tester"; build TestClient(app) for an anonymous one
    yield c
    _teardown()


@pytest.fixture
def live_client(tmp_path: Path, kb: tuple[InMemoryStore, HashEmbedder]) -> Iterator[TestClient]:
    """Context-managed client (one persistent event loop, so background pipeline tasks keep running) + mock LLM."""
    auth = _setup(tmp_path, kb, mock_llm=True)
    with TestClient(app) as c:
        c.headers.update(auth)
        yield c
    _teardown()
