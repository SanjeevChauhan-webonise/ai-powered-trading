from alembic import context
from sqlalchemy import create_engine

from app.core import models as core_models  # noqa: F401  (registers tables)
from app.core.config import get_settings
from app.core.db import Base
from app.data import models  # noqa: F401

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
