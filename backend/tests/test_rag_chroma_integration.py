"""Runs against the real ChromaDB from docker compose (host port 8001); skipped when it is not reachable."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import chromadb
import pytest

from app.core.config import Settings
from app.rag import ingest, retriever
from app.rag.store import ChromaStore
from tests.rag_helpers import HashEmbedder


@pytest.fixture
def chroma_store() -> Iterator[ChromaStore]:
    try:
        client = chromadb.HttpClient(host="localhost", port=8001)
        client.heartbeat()
    except Exception:
        pytest.skip("ChromaDB not reachable on localhost:8001")
    name = f"test_{uuid.uuid4().hex[:8]}"
    yield ChromaStore(client, name)
    client.delete_collection(name)


def test_chroma_ingest_search_idempotent(chroma_store: ChromaStore, tmp_path: Path) -> None:
    emb, settings = HashEmbedder(), Settings(storage_dir=str(tmp_path))
    first = ingest.ingest_all(chroma_store, emb, settings)
    assert chroma_store.count() == first.chunks_total > 50
    assert ingest.ingest_all(chroma_store, emb, settings).chunks_added == 0
    hits = retriever.search(chroma_store, emb, "trailing stop follows the best premium since entry", k=3)
    assert hits[0].source == "risk_management.md" and 0 < hits[0].score <= 1
    assert chroma_store.ids_by_source()["greeks.md"][0] == "builtin"
