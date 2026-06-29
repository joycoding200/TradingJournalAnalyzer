"""add_admin_login_audit

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-29 18:00:00.000000

Add last_login_at / last_login_ip to users for admin login audit (D3.3).
Nullable — only populated on admin login; existing rows stay NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "last_login_at" not in cols:
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    if "last_login_ip" not in cols:
        op.add_column("users", sa.Column("last_login_ip", sa.String(length=45), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "last_login_ip" in cols:
        op.drop_column("users", "last_login_ip")
    if "last_login_at" in cols:
        op.drop_column("users", "last_login_at")
