"""remove paper trading tables

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    for table in ("paper_trades", "paper_orders", "paper_positions", "paper_accounts"):
        op.drop_table(table)


def downgrade() -> None:
    # Paper trading was removed from the app; downgrading does not recreate its tables (see 0005 to rebuild them).
    pass
