"""pipeline_runs

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("dataset_id", sa.String(32), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request", sa.JSON, nullable=False),
        sa.Column("steps", sa.JSON, nullable=False),
        sa.Column("backtest_run_id", sa.String(32), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pipeline_runs")
