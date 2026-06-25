"""add_missing_indexes_defaults

Revision ID: 4b5cc5fa0342
Revises: 8f5363c9321e
Create Date: 2026-06-25 14:00:42.193831

Changes (P1-20, P1-21, P1-22):
  - Add missing indexes: trades.raw_file_id, positions.symbol,
    patterns.pattern_name, analyses(user_id, date_start, date_end)
  - Add NOT NULL + server_default to all timestamp columns
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '4b5cc5fa0342'
down_revision: Union[str, None] = '8f5363c9321e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── P1-20, P1-21: add missing indexes ──
    op.create_index("ix_trades_raw_file_id", "trades", ["raw_file_id"], unique=False)
    op.create_index("ix_positions_symbol", "positions", ["symbol"], unique=False)
    op.create_index("ix_patterns_pattern_name", "patterns", ["pattern_name"], unique=False)
    op.create_index("ix_analyses_user_date_range", "analyses", ["user_id", "date_start", "date_end"], unique=False)

    # ── P1-22: timestamp columns → NOT NULL + server_default ──
    # First, fix any existing NULLs
    op.execute(sa.text("UPDATE users SET created_at = NOW() WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE raw_files SET uploaded_at = NOW() WHERE uploaded_at IS NULL"))
    op.execute(sa.text("UPDATE analyses SET created_at = NOW() WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE reports SET created_at = NOW() WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE case_library SET contributed_at = NOW() WHERE contributed_at IS NULL"))
    op.execute(sa.text("UPDATE daily_bars SET created_at = NOW() WHERE created_at IS NULL"))

    with op.batch_alter_table("users") as batch:
        batch.alter_column("created_at", nullable=False,
                           server_default=sa.func.now(),
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("raw_files") as batch:
        batch.alter_column("uploaded_at", nullable=False,
                           server_default=sa.func.now(),
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("analyses") as batch:
        batch.alter_column("created_at", nullable=False,
                           server_default=sa.func.now(),
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("reports") as batch:
        batch.alter_column("created_at", nullable=False,
                           server_default=sa.func.now(),
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("case_library") as batch:
        batch.alter_column("contributed_at", nullable=False,
                           server_default=sa.func.now(),
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("daily_bars") as batch:
        batch.alter_column("created_at", nullable=False,
                           server_default=sa.func.now(),
                           existing_type=postgresql.TIMESTAMP())


def downgrade() -> None:
    with op.batch_alter_table("daily_bars") as batch:
        batch.alter_column("created_at", nullable=True, server_default=None,
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("case_library") as batch:
        batch.alter_column("contributed_at", nullable=True, server_default=None,
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("reports") as batch:
        batch.alter_column("created_at", nullable=True, server_default=None,
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("analyses") as batch:
        batch.alter_column("created_at", nullable=True, server_default=None,
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("raw_files") as batch:
        batch.alter_column("uploaded_at", nullable=True, server_default=None,
                           existing_type=postgresql.TIMESTAMP())
    with op.batch_alter_table("users") as batch:
        batch.alter_column("created_at", nullable=True, server_default=None,
                           existing_type=postgresql.TIMESTAMP())

    op.drop_index("ix_analyses_user_date_range", table_name="analyses")
    op.drop_index("ix_patterns_pattern_name", table_name="patterns")
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_index("ix_trades_raw_file_id", table_name="trades")
