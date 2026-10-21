from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.rag import ingest, retriever
from app.rag.chunker import MAX_CHARS, chunk_markdown
from app.rag.store import InMemoryStore
from tests.rag_helpers import HashEmbedder, make_pdf


def test_chunker_heading_paths_and_code_fences() -> None:
    md = "# Top\nintro text\n\n## Sub A\nbody a\n\n```\n# not a heading\n```\n\n### Deep\nbody deep\n\n## Sub B\nbody b\n"
    chunks = chunk_markdown(md)
    by_heading = {c.heading: c.text for c in chunks}
    assert by_heading["Top"] == "intro text"
    assert "# not a heading" in by_heading["Top > Sub A"]
    assert by_heading["Top > Sub A > Deep"] == "body deep"
    assert by_heading["Top > Sub B"] == "body b"  # path resets after a deeper section


def test_chunker_splits_long_sections_within_limit() -> None:
    md = "# Long\n" + "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(12))
    chunks = chunk_markdown(md)
    assert len(chunks) > 3
    assert all(len(c.text) <= MAX_CHARS and c.heading == "Long" for c in chunks)
    joined = " ".join(c.text for c in chunks)
    assert all(f"Paragraph {i}." in joined for i in range(12))  # nothing lost


def test_chunker_hard_splits_a_giant_paragraph() -> None:
    chunks = chunk_markdown("# H\n" + "x" * 3000)
    assert len(chunks) >= 4 and all(len(c.text) <= MAX_CHARS for c in chunks)


def test_builtin_docs_are_chunked_and_complete() -> None:
    names = {p.name for p in ingest.BUILTIN_DIR.glob("*.md")}
    assert {
        "options_basics.md",
        "greeks.md",
        "risk_management.md",
        "strategy_ema_crossover.md",
        "strategy_rsi_reversal.md",
    } <= names
    for p in ingest.BUILTIN_DIR.glob("*.md"):
        assert ingest.read_chunks(p), p.name


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(storage_dir=str(tmp_path / "storage"))


def test_ingest_all_is_idempotent(settings: Settings, kb: tuple[InMemoryStore, HashEmbedder]) -> None:
    store, emb = kb
    first = ingest.ingest_all(store, emb, settings)
    assert first.documents >= 10 and first.chunks_added == first.chunks_total == store.count()
    embedded = emb.embedded
    second = ingest.ingest_all(store, emb, settings)
    assert second.chunks_added == 0 and second.chunks_removed == 0 and second.chunks_total == first.chunks_total
    assert store.count() == first.chunks_total and emb.embedded == embedded  # nothing re-embedded


def test_changed_and_removed_uploads(settings: Settings, kb: tuple[InMemoryStore, HashEmbedder]) -> None:
    store, emb = kb
    up = ingest.upload_dir(settings)
    up.mkdir(parents=True)
    note = up / "note.md"
    note.write_text("# Note\n\nAlpha section text.\n\n## Two\n\nBeta section text.\n")
    base = ingest.ingest_all(store, emb, settings)
    note.write_text("# Note\n\nAlpha section text.\n\n## Two\n\nGamma replaced text.\n")
    embedded = emb.embedded
    changed = ingest.ingest_all(store, emb, settings)
    assert (changed.chunks_added, changed.chunks_removed) == (1, 1)  # only the edited chunk
    assert emb.embedded == embedded + 1
    assert changed.chunks_total == base.chunks_total
    texts = {h.text for h in store.query(emb.embed(["gamma"])[0], 100)}
    assert "Gamma replaced text." in texts and "Beta section text." not in texts

    note.unlink()
    gone = ingest.ingest_all(store, emb, settings)
    assert gone.sources_removed == ["uploads/note.md"] and gone.chunks_removed == 2
    assert "uploads/note.md" not in store.ids_by_source()


def test_retrieval_returns_relevant_sources_with_metadata(
    settings: Settings, kb: tuple[InMemoryStore, HashEmbedder]
) -> None:
    store, emb = kb
    ingest.ingest_all(store, emb, settings)
    hits = retriever.search(store, emb, "trailing stop follows the best premium since entry", k=3)
    assert hits[0].source == "risk_management.md" and "Trailing" in hits[0].heading
    assert hits[0].doc_type == "builtin" and 0 < hits[0].score <= 1
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    greeks = retriever.search(store, emb, "gamma theta vega delta sensitivity", k=3)
    assert greeks[0].source == "greeks.md"
    rsi = retriever.search(store, emb, "RSI crosses back above 30 oversold reversal", k=3)
    assert {"strategy_rsi_reversal.md", "indicators_momentum.md"} & {h.source for h in rsi}


def test_search_empty_store(kb: tuple[InMemoryStore, HashEmbedder]) -> None:
    assert retriever.search(*kb, "anything") == []


# ---- API ---------------------------------------------------------------------------------------


def test_api_ingest_documents_search(client: TestClient) -> None:
    assert client.get("/knowledge/documents").json() == []
    rep = client.post("/knowledge/ingest").json()
    assert rep["documents"] >= 10 and rep["chunks_added"] == rep["chunks_total"] > 50
    docs = client.get("/knowledge/documents").json()
    assert {d["source"] for d in docs} >= {"greeks.md", "risk_management.md"} and all(
        d["doc_type"] == "builtin" for d in docs
    )
    res = client.post("/knowledge/search", json={"query": "what is a trailing stop loss", "k": 2}).json()
    assert len(res) == 2 and res[0]["source"] == "risk_management.md"
    assert set(res[0]) == {"text", "score", "source", "heading", "doc_type"}
    assert client.post("/knowledge/search", json={"query": ""}).status_code == 422
    assert client.post("/knowledge/search", json={"query": "x", "k": 99}).status_code == 422
    assert client.post("/knowledge/ingest").json()["chunks_added"] == 0


def test_api_upload_markdown_and_reingest_keeps_it(client: TestClient) -> None:
    r = client.post(
        "/knowledge/upload",
        files={"file": ("my notes.md", b"# Iron condor\n\nSell OTM call and put spreads for credit.\n")},
    )
    assert r.status_code == 200 and r.json() == {"source": "uploads/my notes.md", "chunks": 1}
    hit = client.post("/knowledge/search", json={"query": "iron condor credit spreads", "k": 1}).json()[0]
    assert hit["source"] == "uploads/my notes.md" and hit["doc_type"] == "uploaded"
    assert client.post("/knowledge/ingest").json()["chunks_removed"] == 0  # upload survives a re-ingest
    assert any(d["source"] == "uploads/my notes.md" for d in client.get("/knowledge/documents").json())
    again = client.post(
        "/knowledge/upload", files={"file": ("my notes.md", b"# Iron condor\n\nCompletely different text now.\n")}
    )
    assert again.status_code == 200
    docs = {d["source"]: d["chunks"] for d in client.get("/knowledge/documents").json()}
    assert docs["uploads/my notes.md"] == 1  # replaced, not duplicated


def test_api_upload_pdf(client: TestClient) -> None:
    r = client.post(
        "/knowledge/upload", files={"file": ("guide.pdf", make_pdf("Calendar spreads exploit differing theta decay"))}
    )
    assert r.status_code == 200, r.text
    hit = client.post("/knowledge/search", json={"query": "calendar spreads theta decay", "k": 1}).json()[0]
    assert hit["source"] == "uploads/guide.pdf" and hit["heading"] == "Page 1"


def test_api_upload_rejections(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def up(name: str, data: bytes) -> int:
        return client.post("/knowledge/upload", files={"file": (name, data)}).status_code

    assert up("notes.txt", b"hello") == 400
    assert up("../evil.md", b"# x\n\ny") == 200  # directory part is stripped, never written outside the upload dir
    assert (tmp_path / "storage" / "knowledge" / "evil.md").exists() and not (tmp_path / "storage" / "evil.md").exists()
    assert up(".hidden.md", b"# x\n\ny") == 400
    assert up("empty.md", b"   \n") == 400  # no text
    assert up("broken.pdf", b"%PDF-1.4 definitely not a pdf") == 400
    kdir = tmp_path / "storage" / "knowledge"
    assert not (kdir / "empty.md").exists() and not (kdir / "broken.pdf").exists()  # rejected files are not kept
    monkeypatch.setattr("app.api.knowledge.MAX_UPLOAD_BYTES", 10)
    assert up("big.md", b"# big\n\n" + b"x" * 50) == 413


def test_api_store_failure_is_503(client: TestClient) -> None:
    from app.api.deps import get_vector_store
    from app.main import app

    class Broken:
        def count(self) -> int:
            raise ConnectionError("chroma down")

        ids_by_source = query = upsert = delete = count

    app.dependency_overrides[get_vector_store] = lambda: Broken()
    for call in (
        lambda: client.post("/knowledge/ingest"),
        lambda: client.post("/knowledge/search", json={"query": "x"}),
        lambda: client.get("/knowledge/documents"),
    ):
        r = call()
        assert r.status_code == 503 and "unavailable" in r.json()["detail"]
