from app.rag.embeddings import Embedder
from app.rag.store import VectorStore
from app.schemas.rag import RetrievedChunk


def search(store: VectorStore, embedder: Embedder, query: str, k: int = 5) -> list[RetrievedChunk]:
    """Top-k chunks for a query, with source metadata."""
    hits = store.query(embedder.embed([query])[0], k)
    return [
        RetrievedChunk(
            text=h.text,
            score=round(h.score, 4),
            source=str(h.metadata["source"]),
            heading=str(h.metadata.get("heading", "")),
            doc_type=h.metadata["doc_type"],
        )
        for h in hits
    ]
