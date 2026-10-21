from pathlib import Path

import pandas as pd

from app.schemas.data import DatasetKind


def frame_path(storage_dir: str, dataset_id: str, kind: DatasetKind) -> Path:
    return Path(storage_dir) / dataset_id / f"{kind}.parquet"


def write_frame(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def read_frame(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(path, columns=columns)
