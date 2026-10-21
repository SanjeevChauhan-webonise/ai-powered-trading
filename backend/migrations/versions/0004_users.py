"""users, auth sessions, and per-user ownership of strategies / backtests / runs

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"

OWNED = ("strategies", "backtest_runs", "pipeline_runs")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("level", sa.String(12), nullable=False, server_default="beginner"),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )
    for table in OWNED:  # existing rows stay unowned (NULL) until otj/seed_users.py assigns them
        op.add_column(table, sa.Column("user_id", sa.String(32), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:
    for table in OWNED:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
    op.drop_table("auth_sessions")
    op.drop_table("users")
