"""add stock_sync and price_sync to synctype enum

Revision ID: 003
Revises: 002
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, str, None] = None
depends_on: Union[str, str, None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE synctype ADD VALUE 'stock_sync'")
    op.execute("ALTER TYPE synctype ADD VALUE 'price_sync'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # A full rebuild would be required; skipping for simplicity.
    pass
