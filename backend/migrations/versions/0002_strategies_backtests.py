"""strategies and backtest_runs

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("dataset_id", sa.String(32), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(32), nullable=True),
        sa.Column("strategy_name", sa.String(200), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("start", sa.Date, nullable=True),
        sa.Column("end", sa.Date, nullable=True),
        sa.Column("capital", sa.Float, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("total_pnl", sa.Float, nullable=True),
        sa.Column("num_trades", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("backtest_runs")
    op.drop_table("strategies")
