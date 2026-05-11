"""initial schema - products, listings, orders, price_history, sync_log

Revision ID: 001
Revises: None
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, str, None] = None
depends_on: Union[str, str, None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asin", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=200), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("detail_page_url", sa.Text(), nullable=True),
        sa.Column("amazon_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("current_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("source", sa.Enum("amazon", name="productsource"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asin"),
    )
    op.create_index("ix_products_asin", "products", ["asin"])

    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("ebay_item_id", sa.String(length=50), nullable=True),
        sa.Column("ebay_sku", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("listing_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_sold", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("draft", "active", "ended", "sold", name="listingstatus"), nullable=False),
        sa.Column("ebay_category_id", sa.String(length=50), nullable=True),
        sa.Column("listing_duration", sa.String(length=20), nullable=True),
        sa.Column("ebay_fee_estimate", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ebay_item_id"),
    )
    op.create_index("ix_listing_product_id", "listings", ["product_id"])
    op.create_index("ix_listing_status_product", "listings", ["status", "product_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("ebay_order_id", sa.String(length=50), nullable=True),
        sa.Column("buyer_username", sa.String(length=100), nullable=True),
        sa.Column("sale_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("ebay_fee", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("status", sa.Enum("pending", "shipped", "delivered", "cancelled", "returned", name="orderstatus"), nullable=False),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ebay_order_id"),
    )
    op.create_index("ix_order_listing_id", "orders", ["listing_id"])
    op.create_index("ix_order_status_ebay", "orders", ["status", "ebay_order_id"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_product_recorded", "price_history", ["product_id", "recorded_at"])

    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sync_type", sa.Enum("amazon_product", "ebay_listing", "ebay_order", "price_refresh", name="synctype"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", name="syncstatus"), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False),
        sa.Column("records_succeeded", sa.Integer(), nullable=False),
        sa.Column("records_failed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_type_status", "sync_log", ["sync_type", "status"])


def downgrade() -> None:
    op.drop_table("sync_log")
    op.drop_table("price_history")
    op.drop_table("orders")
    op.drop_table("listings")
    op.drop_table("products")

    op.execute("DROP TYPE IF EXISTS syncstatus")
    op.execute("DROP TYPE IF EXISTS synctype")
    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS listingstatus")
    op.execute("DROP TYPE IF EXISTS productsource")