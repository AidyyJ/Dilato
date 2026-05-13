from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, Enum, ForeignKey, Index, Numeric
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProductSource(PyEnum):
    amazon = "amazon"


class ListingStatus(PyEnum):
    draft = "draft"
    active = "active"
    ended = "ended"
    sold = "sold"


class OrderStatus(PyEnum):
    pending = "pending"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"
    returned = "returned"


class FulfillmentStatus(PyEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    delivered = "delivered"


class SyncStatus(PyEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class SyncType(PyEnum):
    amazon_product = "amazon_product"
    ebay_listing = "ebay_listing"
    ebay_order = "ebay_order"
    price_refresh = "price_refresh"
    stock_sync = "stock_sync"
    price_sync = "price_sync"


class RuleType(PyEnum):
    fixed_markup = "fixed_markup"
    percentage = "percentage"
    fixed_price = "fixed_price"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asin = Column(String(20), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    brand = Column(String(200), nullable=True)
    category = Column(String(200), nullable=True)
    image_url = Column(Text, nullable=True)
    detail_page_url = Column(Text, nullable=True)
    amazon_price = Column(Numeric(10, 2), nullable=True)
    current_price = Column(Numeric(10, 2), nullable=True)
    source = Column(Enum(ProductSource), default=ProductSource.amazon, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    listings = relationship("Listing", back_populates="product", lazy="selectin")
    price_history = relationship("PriceHistory", back_populates="product", lazy="selectin", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    ebay_item_id = Column(String(50), unique=True, nullable=True, index=True)
    ebay_sku = Column(String(50), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    listing_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    quantity_sold = Column(Integer, default=0, nullable=False)
    status = Column(Enum(ListingStatus), default=ListingStatus.draft, nullable=False, index=True)
    ebay_category_id = Column(String(50), nullable=True)
    listing_duration = Column(String(20), default="GTC", nullable=True)
    ebay_fee_estimate = Column(Numeric(8, 2), nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="listings")
    orders = relationship("Order", back_populates="listing", lazy="selectin")

    __table_args__ = (
        Index("ix_listing_status_product", "status", "product_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(Integer, ForeignKey("listings.id", ondelete="SET NULL"), nullable=True, index=True)
    ebay_order_id = Column(String(50), unique=True, nullable=True, index=True)
    buyer_username = Column(String(100), nullable=True)
    sale_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    shipping_cost = Column(Numeric(8, 2), nullable=True, default=0)
    ebay_fee = Column(Numeric(8, 2), nullable=True, default=0)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending, nullable=False, index=True)
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    # webhook / fulfillment extensions
    shipping_address = Column(Text, nullable=True)
    payment_status = Column(String(50), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    carrier = Column(String(100), nullable=True)
    raw_payload = Column(Text, nullable=True)
    last_webhook_at = Column(DateTime, nullable=True)
    # purchase / profit tracking
    amazon_purchase_url = Column(Text, nullable=True)
    purchase_cost = Column(Numeric(10, 2), nullable=True)
    profit = Column(Numeric(10, 2), nullable=True)
    margin_percent = Column(Numeric(5, 2), nullable=True)
    amazon_order_id = Column(String(50), nullable=True)
    purchased_at = Column(DateTime, nullable=True)
    fulfillment_status = Column(Enum(FulfillmentStatus), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    listing = relationship("Listing", back_populates="orders")

    __table_args__ = (
        Index("ix_order_status_ebay", "status", "ebay_order_id"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    source = Column(String(50), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    product = relationship("Product", back_populates="price_history")

    __table_args__ = (
        Index("ix_price_product_recorded", "product_id", "recorded_at"),
    )


class SyncLog(Base):
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(Enum(SyncType), nullable=False, index=True)
    status = Column(Enum(SyncStatus), default=SyncStatus.pending, nullable=False, index=True)
    records_processed = Column(Integer, default=0, nullable=False)
    records_succeeded = Column(Integer, default=0, nullable=False)
    records_failed = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_sync_type_status", "sync_type", "status"),
    )


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    rule_type = Column(Enum(RuleType), nullable=False)
    value = Column(Numeric(10, 2), nullable=False)
    min_price = Column(Numeric(10, 2), nullable=True)
    max_price = Column(Numeric(10, 2), nullable=True)
    min_margin_percent = Column(Numeric(5, 2), nullable=True)
    priority = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_pricing_rule_active_priority", "is_active", "priority"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)