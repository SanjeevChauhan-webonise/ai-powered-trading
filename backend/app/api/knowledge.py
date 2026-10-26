import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import Cfg, Emb, Store
from app.rag import ingest, retriever
from app.schemas.rag import (
    ChunkOut,
    ChunkPage,
    DocumentInfo,
    IngestReport,
    RetrievedChunk,
    SearchRequest,
    UploadResponse,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[\w][\w .\-()]{0,150}$")


@contextmanager
def _kb_errors() -> Iterator[None]:
    """Vector store / embedding model problems become a 503; bad documents a 400."""
    try:
        yield
    except ingest.DocumentError as e:
        raise HTTPException(400, str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        log.exception("knowledge base error")
        raise HTTPException(503, f"Knowledge base unavailable: {type(e).__name__}: {e}") from e


@router.post("/ingest", response_model=IngestReport, summary="Re-ingest built-in docs and uploads")
def reingest(settings: Cfg, store: Store, embedder: Emb) -> IngestReport:
    with _kb_errors():
        return ingest.ingest_all(store, embedder, settings)


@router.post("/upload", response_model=UploadResponse, summary="Upload a .md or .pdf document")
def upload(
    settings: Cfg, store: Store, embedder: Emb, file: Annotated[UploadFile, File(description=".md or .pdf")]
) -> UploadResponse:
    name = Path(file.filename or "").name
    if not _SAFE_NAME.match(name) or Path(name).suffix.lower() not in (".md", ".pdf"):
        raise HTTPException(400, "Upload a .md or .pdf file with a simple file name")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 10 MB)")
    dest = ingest.upload_dir(settings) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    existed = dest.exists()
    previous = dest.read_bytes() if existed else None
    dest.write_bytes(data)
    src = ingest.Source(f"{ingest.UPLOAD_PREFIX}{name}", dest, "uploaded")
    try:
        with _kb_errors():
            total, _, _ = ingest.ingest_source(store, embedder, src)
    except HTTPException:
        # roll back so a bad/unindexed file doesn't linger and get picked up by the next re-ingest
        if previous is not None:
            dest.write_bytes(previous)
        else:
            dest.unlink(missing_ok=True)
        raise
    return UploadResponse(source=src.name, chunks=total)


@router.post("/search", response_model=list[RetrievedChunk], summary="Retrieve relevant chunks (no LLM)")
def search(req: SearchRequest, store: Store, embedder: Emb) -> list[RetrievedChunk]:
    with _kb_errors():
        return retriever.search(store, embedder, req.query, req.k)


@router.get("/documents", response_model=list[DocumentInfo], summary="Ingested sources")
def documents(store: Store) -> list[DocumentInfo]:
    with _kb_errors():
        return [
            DocumentInfo(source=s, doc_type=t, chunks=len(ids)) for s, (t, ids) in sorted(store.ids_by_source().items())
        ]


@router.get("/chunks", response_model=ChunkPage, summary="Browse the stored chunks of one source, in document order")
def chunks(store: Store, source: str, offset: int = 0, limit: int = 20) -> ChunkPage:
    limit = max(1, min(limit, 100))
    with _kb_errors():
        known = store.ids_by_source().get(source)
        if known is None:
            raise HTTPException(404, f"Unknown source '{source}'")
        rows = store.chunks_of(source, max(0, offset), limit)
        return ChunkPage(
            source=source,
            total=len(known[1]),
            offset=max(0, offset),
            chunks=[
                ChunkOut(
                    id=i,
                    source=source,
                    heading=str(m.get("heading", "")),
                    chunk_index=int(m.get("chunk_index", 0)),
                    text=t,
                )
                for i, t, m in rows
            ],
        )
