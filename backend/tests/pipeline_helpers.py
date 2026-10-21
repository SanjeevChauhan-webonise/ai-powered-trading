import uuid
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import Base
from app.core.models import PipelineRun
from app.data import service
from app.data.synthetic import SyntheticConfig, generate
from app.rag import ingest
from app.rag.store import InMemoryStore
from app.schemas.agents import STEP_ORDER, RunRequest, StepRecord
from app.schemas.data import ColumnMapping
from tests.rag_helpers import HashEmbedder


@lru_cache
def synthetic() -> tuple[pd.DataFrame, pd.DataFrame]:
    return generate(SyntheticConfig(trading_days=6, n_strikes=4))


class Env:
    def __init__(self, tmp_path: Path, mock_llm: bool = True, **settings: object) -> None:
        settings.setdefault("default_model", "mock:demo" if mock_llm else "openai:gpt-4o-mini")
        self.settings = Settings(storage_dir=str(tmp_path / "storage"), enable_mock_llm=mock_llm, **settings)  # type: ignore[arg-type]
        engine = create_engine(f"sqlite:///{tmp_path / 'env.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.maker: Callable[[], Session] = sessionmaker(bind=engine)
        self.store, self.embedder = InMemoryStore(), HashEmbedder()
        ingest.ingest_all(self.store, self.embedder, self.settings)
        under, opts = synthetic()
        with self.maker() as s:
            row = service.ingest(
                s, self.settings, under, kind="underlying", mapping=ColumnMapping.standard("underlying"),
                underlying="NIFTY", lot_size=75, name="t",
            )  # fmt: skip
            row = service.ingest(
                s, self.settings, opts, kind="options", mapping=ColumnMapping.standard("options"),
                underlying="NIFTY", dataset_id=row.id,
            )  # fmt: skip
            self.dataset_id = row.id

    def create_run(self, **req: object) -> str:
        request = RunRequest.model_validate({"dataset_id": self.dataset_id, **req})
        with self.maker() as s:
            row = PipelineRun(
                id=uuid.uuid4().hex, dataset_id=self.dataset_id, status="queued",
                request=request.model_dump(mode="json"),
                steps=[StepRecord(name=n).model_dump(mode="json") for n in STEP_ORDER],
            )  # fmt: skip
            s.add(row)
            s.commit()
            return row.id

    def run(self, run_id: str) -> PipelineRun:
        with self.maker() as s:
            row = s.get(PipelineRun, run_id)
            assert row is not None
            s.expunge(row)
            return row
