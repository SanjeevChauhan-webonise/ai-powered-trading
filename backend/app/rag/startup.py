import logging
import threading
import time

from app.core.config import Settings
from app.rag.embeddings import get_embedder
from app.rag.ingest import ingest_all
from app.rag.store import get_store

log = logging.getLogger(__name__)


def _autoingest(settings: Settings, attempts: int = 10, delay: float = 3.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            store = get_store()
            if store.count() > 0:
                log.info("knowledge base already populated (%d chunks)", store.count())
                return
            report = ingest_all(store, get_embedder(), settings)
            log.info("knowledge base ingested: %s", report.model_dump())
            return
        except Exception as e:
            log.warning("knowledge auto-ingest attempt %d/%d failed: %s", attempt, attempts, e)
            time.sleep(delay)
    log.warning("knowledge auto-ingest gave up; POST /knowledge/ingest once ChromaDB/the embedding model are available")


def start_autoingest(settings: Settings) -> None:
    """Populate an empty knowledge base in the background; never blocks or breaks app startup."""
    threading.Thread(target=_autoingest, args=(settings,), daemon=True, name="rag-autoingest").start()
