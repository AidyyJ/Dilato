"""add order webhook and fulfillment columns

Revision ID: 005
Revises: 004_add_users
Create Date: 2026-05-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004_add_users"
branch_labels: Union[str, str, None] = None
depends_on: Union[str, str, None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("shipping_address", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("payment_status", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("tracking_number", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("carrier", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("raw_payload", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("last_webhook_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("amazon_purchase_url", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("purchase_cost", sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column("orders", sa.Column("profit", sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column("orders", sa.Column("margin_percent", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("orders", sa.Column("amazon_order_id", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("purchased_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("fulfillment_status", sa.Enum("not_started", "in_progress", "delivered", name="fulfillmentstatus"), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "fulfillment_status")
    op.drop_column("orders", "purchased_at")
    op.drop_column("orders", "amazon_order_id")
    op.drop_column("orders", "margin_percent")
    op.drop_column("orders", "profit")
    op.drop_column("orders", "purchase_cost")
    op.drop_column("orders", "amazon_purchase_url")
    op.drop_column("orders", "last_webhook_at")
    op.drop_column("orders", "raw_payload")
    op.drop_column("orders", "carrier")
    op.drop_column("orders", "tracking_number")
    op.drop_column("orders", "payment_status")
    op.drop_column("orders", "shipping_address")
