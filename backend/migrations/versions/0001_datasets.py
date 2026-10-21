"""create datasets table

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("underlying", sa.String(50), nullable=False),
        sa.Column("lot_size", sa.Integer, nullable=False),
        sa.Column("timeframe_minutes", sa.Integer, nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("underlying_rows", sa.Integer, nullable=False),
        sa.Column("options_rows", sa.Integer, nullable=False),
        sa.Column("expiries", sa.JSON, nullable=False),
        sa.Column("strikes", sa.JSON, nullable=False),
        sa.Column("quality", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("datasets")
