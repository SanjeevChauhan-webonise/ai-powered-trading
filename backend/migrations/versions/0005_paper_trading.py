"""paper trading: accounts, positions, orders, trades

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def _contract() -> list[sa.Column]:
    return [
        sa.Column("dataset_id", sa.String(32), nullable=False),
        sa.Column("underlying", sa.String(50), nullable=False),
        sa.Column("expiry", sa.Date, nullable=False),
        sa.Column("strike", sa.Float, nullable=False),
        sa.Column("option_type", sa.String(2), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("starting_balance", sa.Float, nullable=False),
        sa.Column("cash", sa.Float, nullable=False),
        sa.Column("dataset_id", sa.String(32), nullable=True),
        sa.Column("clock_time", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "paper_positions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("account_id", sa.String(32), nullable=False, index=True),
        sa.Column("user_id", sa.String(32), nullable=False, index=True),
        *_contract(),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("avg_price", sa.Float, nullable=False),
        sa.Column("stop_pct", sa.Float, nullable=True),
        sa.Column("target_pct", sa.Float, nullable=True),
        sa.Column("square_off", sa.String(5), nullable=True),
        sa.Column("run_id", sa.String(32), nullable=True),
        sa.Column("opened_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("account_id", sa.String(32), nullable=False, index=True),
        sa.Column("user_id", sa.String(32), nullable=False, index=True),
        *_contract(),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("run_id", sa.String(32), nullable=True),
        sa.Column("placed_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True),
    )
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("account_id", sa.String(32), nullable=False, index=True),
        sa.Column("user_id", sa.String(32), nullable=False, index=True),
        *_contract(),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=False),
        sa.Column("entry_time", sa.DateTime, nullable=False),
        sa.Column("exit_time", sa.DateTime, nullable=False),
        sa.Column("gross_pnl", sa.Float, nullable=False),
        sa.Column("costs", sa.Float, nullable=False),
        sa.Column("net_pnl", sa.Float, nullable=False),
        sa.Column("exit_reason", sa.String(12), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True),
    )


def downgrade() -> None:
    for t in ("paper_trades", "paper_orders", "paper_positions", "paper_accounts"):
        op.drop_table(t)
