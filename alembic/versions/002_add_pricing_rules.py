"""Add pricing_rules table

Revision ID: 002
Revises: 001
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, str, None] = None
depends_on: Union[str, str, None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("rule_type", sa.Enum("fixed_markup", "percentage", "fixed_price", name="ruletype"), nullable=False),
        sa.Column("value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("min_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("max_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("min_margin_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_rule_type", "pricing_rules", ["rule_type"])
    op.create_index("ix_pricing_rule_active_priority", "pricing_rules", ["is_active", "priority"])


def downgrade() -> None:
    op.drop_index("ix_pricing_rule_active_priority", table_name="pricing_rules")
    op.drop_index("ix_pricing_rule_type", table_name="pricing_rules")
    op.drop_table("pricing_rules")
    op.execute("DROP TYPE IF EXISTS ruletype")
