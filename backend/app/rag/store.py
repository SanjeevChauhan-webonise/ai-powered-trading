import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import chromadb

from app.core.config import get_settings


@dataclass(frozen=True)
class Hit:
    text: str
    score: float
    metadata: dict[str, Any]


class VectorStore(Protocol):
    def upsert(
        self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]
    ) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def query(self, embedding: list[float], k: int) -> list[Hit]: ...
    def ids_by_source(self) -> dict[str, tuple[str, set[str]]]:
        """source -> (doc_type, chunk ids)"""
        ...

    def count(self) -> int: ...


class ChromaStore:
    def __init__(self, client: Any, collection: str) -> None:
        # cosine space so score = 1 - distance
        self._col = client.get_or_create_collection(name=collection, metadata={"hnsw:space": "cosine"})

    def upsert(
        self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]
    ) -> None:
        if ids:
            self._col.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._col.delete(ids=ids)

    def query(self, embedding: list[float], k: int) -> list[Hit]:
        n = self._col.count()
        if n == 0:
            return []
        res = self._col.query(
            query_embeddings=[embedding], n_results=min(k, n), include=["documents", "metadatas", "distances"]
        )
        return [
            Hit(text=d, score=1.0 - float(dist), metadata=dict(m))
            for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True)
        ]

    def ids_by_source(self) -> dict[str, tuple[str, set[str]]]:
        got = self._col.get(include=["metadatas"])
        out: dict[str, tuple[str, set[str]]] = {}
        for cid, meta in zip(got["ids"], got["metadatas"], strict=True):
            doc_type, ids = out.setdefault(str(meta["source"]), (str(meta["doc_type"]), set()))
            ids.add(cid)
        return out

    def count(self) -> int:
        return int(self._col.count())


class InMemoryStore:
    """Test double with the same semantics (cosine similarity)."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, list[float], dict[str, Any]]] = {}

    def upsert(
        self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]
    ) -> None:
        for i, t, e, m in zip(ids, texts, embeddings, metadatas, strict=True):
            self._rows[i] = (t, e, m)

    def delete(self, ids: list[str]) -> None:
        for i in ids:
            self._rows.pop(i, None)

    def query(self, embedding: list[float], k: int) -> list[Hit]:
        def cos(a: list[float], b: list[float]) -> float:
            na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
            return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0

        hits = [Hit(t, cos(embedding, e), dict(m)) for t, e, m in self._rows.values()]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:k]

    def ids_by_source(self) -> dict[str, tuple[str, set[str]]]:
        out: dict[str, tuple[str, set[str]]] = {}
        for cid, (_, _, m) in self._rows.items():
            out.setdefault(m["source"], (m["doc_type"], set()))[1].add(cid)
        return out

    def count(self) -> int:
        return len(self._rows)


def collection_name(base: str, embedding_model: str) -> str:
    """One collection per embedding model so vector dimensions never clash."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", embedding_model).strip("_").lower()
    return f"{base}_{slug}"[:63]


@lru_cache
def get_store() -> VectorStore:
    s = get_settings()
    client = chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port)
    return ChromaStore(client, collection_name(s.rag_collection, s.embedding_model))
