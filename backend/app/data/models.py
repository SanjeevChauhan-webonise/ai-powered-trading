from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    underlying: Mapped[str] = mapped_column(String(50))
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    timeframe_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    underlying_rows: Mapped[int] = mapped_column(Integer, default=0)
    options_rows: Mapped[int] = mapped_column(Integer, default=0)
    expiries: Mapped[list[str]] = mapped_column(JSON, default=list)
    strikes: Mapped[list[float]] = mapped_column(JSON, default=list)
    quality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
