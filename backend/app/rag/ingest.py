import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.core.config import Settings
from app.rag.chunker import Chunk, chunk_markdown
from app.rag.embeddings import Embedder
from app.rag.store import VectorStore
from app.schemas.rag import DocType, IngestReport

log = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).parent / "docs"
UPLOAD_PREFIX = "uploads/"
BATCH = 64


class DocumentError(ValueError):
    """A document could not be read or has no usable text."""


@dataclass(frozen=True)
class Source:
    name: str  # stored as metadata "source"
    path: Path
    doc_type: DocType


def upload_dir(settings: Settings) -> Path:
    return Path(settings.storage_dir) / "knowledge"


def collect_sources(settings: Settings) -> list[Source]:
    out = [Source(p.name, p, "builtin") for p in sorted(BUILTIN_DIR.glob("*.md"))] if settings.rag_builtin_docs else []
    up = upload_dir(settings)
    if up.exists():
        out += [
            Source(f"{UPLOAD_PREFIX}{p.name}", p, "uploaded")
            for p in sorted(up.iterdir())
            if p.suffix.lower() in (".md", ".pdf")
        ]
    return out


def read_chunks(path: Path) -> list[Chunk]:
    try:
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(str(path))
            chunks: list[Chunk] = []
            for n, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                chunks += [Chunk(c.text, f"Page {n}") for c in chunk_markdown(text)] if text else []
        else:
            chunks = chunk_markdown(path.read_text(encoding="utf-8"))
    except DocumentError:
        raise
    except Exception as e:
        raise DocumentError(f"Could not read {path.name}: {e}") from e
    if not chunks:
        raise DocumentError(f"{path.name} has no extractable text")
    return chunks


def _chunk_id(source: str, index: int, text: str) -> str:
    return hashlib.sha1(f"{source}\x00{index}\x00{text}".encode()).hexdigest()[:20]


def ingest_source(store: VectorStore, embedder: Embedder, src: Source) -> tuple[int, int, int]:
    """Make the store match this source. Unchanged chunks are not re-embedded. Returns (total, added, removed)."""
    chunks = read_chunks(src.path)
    wanted = {_chunk_id(src.name, i, c.text): (i, c) for i, c in enumerate(chunks)}
    existing = store.ids_by_source().get(src.name, (src.doc_type, set()))[1]
    stale = sorted(existing - wanted.keys())
    new_ids = [cid for cid in wanted if cid not in existing]
    store.delete(stale)
    for i in range(0, len(new_ids), BATCH):
        batch = new_ids[i : i + BATCH]
        items = [wanted[cid] for cid in batch]
        vectors = embedder.embed([f"{c.heading}\n{c.text}" if c.heading else c.text for _, c in items])
        store.upsert(
            batch,
            [c.text for _, c in items],
            vectors,
            [
                {"source": src.name, "doc_type": src.doc_type, "heading": c.heading, "chunk_index": idx}
                for idx, c in items
            ],
        )
    return len(wanted), len(new_ids), len(stale)


def ingest_all(store: VectorStore, embedder: Embedder, settings: Settings) -> IngestReport:
    """Sync the store with built-in docs + uploads; sources that disappeared from disk are removed."""
    sources = collect_sources(settings)
    total = added = removed = docs = 0
    for src in sources:
        try:
            t, a, r = ingest_source(store, embedder, src)
        except DocumentError as e:
            log.warning("skipping %s: %s", src.name, e)
            continue
        docs, total, added, removed = docs + 1, total + t, added + a, removed + r
    present = {s.name for s in sources}
    gone = sorted(set(store.ids_by_source()) - present)
    for name in gone:
        ids = store.ids_by_source()[name][1]
        store.delete(sorted(ids))
        removed += len(ids)
    return IngestReport(
        documents=docs, chunks_total=total, chunks_added=added, chunks_removed=removed, sources_removed=gone
    )
