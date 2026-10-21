from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["builtin", "uploaded"]


class RetrievedChunk(BaseModel):
    text: str
    score: float = Field(description="Cosine similarity, higher is more relevant")
    source: str
    heading: str
    doc_type: DocType


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(5, ge=1, le=20)


class IngestReport(BaseModel):
    documents: int
    chunks_total: int
    chunks_added: int
    chunks_removed: int
    sources_removed: list[str]


class UploadResponse(BaseModel):
    source: str
    chunks: int


class DocumentInfo(BaseModel):
    source: str
    doc_type: DocType
    chunks: int
