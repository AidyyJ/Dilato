from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.models import (
    ProductSource,
    ListingStatus,
    OrderStatus,
    FulfillmentStatus,
    SyncStatus,
    SyncType,
    RuleType,
)


class ProductBase(BaseModel):
    asin: str = Field(..., max_length=20)
    title: str = Field(..., max_length=500)
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    detail_page_url: Optional[str] = None
    amazon_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None

    @field_validator("detail_page_url", "image_url")
    @classmethod
    def validate_url_scheme(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        scheme = urlparse(v).scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError(f"URL must use http or https scheme, got: {v}")
        return v


class ProductCreate(ProductBase):
    pass


class ProductOut(ProductBase):
    id: int
    source: ProductSource
    is_active: bool
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ListingBase(BaseModel):
    title: str = Field(..., max_length=500)
    listing_price: Decimal
    quantity: int = 1
    ebay_category_id: Optional[str] = None
    listing_duration: str = "GTC"


class ListingCreate(ListingBase):
    product_id: int
    listing_price: Optional[Decimal] = None  # auto-calculated if omitted

    @field_validator("listing_price")
    @classmethod
    def listing_price_must_be_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("listing_price must be greater than 0")
        return v

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v


class ListingCreateFromProduct(BaseModel):
    product_id: int
    pricing_rule_id: Optional[int] = None


class ListingPublishOut(BaseModel):
    listing_id: int
    ebay_item_id: Optional[str] = None
    status: str


class ListingOut(ListingBase):
    id: int
    product_id: int
    ebay_item_id: Optional[str] = None
    ebay_sku: Optional[str] = None
    quantity_sold: int
    status: ListingStatus
    ebay_fee_estimate: Optional[Decimal] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    sale_price: Decimal
    quantity: int = 1
    shipping_cost: Optional[Decimal] = Decimal("0")
    ebay_fee: Optional[Decimal] = Decimal("0")


class OrderCreate(BaseModel):
    ebay_order_id: str = Field(..., max_length=50)
    listing_id: Optional[int] = None
    sale_price: Decimal
    quantity: int = 1
    shipping_cost: Optional[Decimal] = Decimal("0")
    ebay_fee: Optional[Decimal] = Decimal("0")


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    amazon_purchase_url: Optional[str] = None
    purchase_cost: Optional[Decimal] = None
    amazon_order_id: Optional[str] = Field(None, max_length=50)
    fulfillment_status: Optional[FulfillmentStatus] = None


class OrderOut(OrderBase):
    id: int
    listing_id: Optional[int] = None
    ebay_order_id: Optional[str] = None
    buyer_username: Optional[str] = None
    status: OrderStatus
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    shipping_address: Optional[str] = None
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    last_webhook_at: Optional[datetime] = None
    amazon_purchase_url: Optional[str] = None
    purchase_cost: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    margin_percent: Optional[Decimal] = None
    amazon_order_id: Optional[str] = None
    purchased_at: Optional[datetime] = None
    fulfillment_status: Optional[FulfillmentStatus] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderProfitOut(BaseModel):
    sale_price: Decimal
    shipping_cost: Optional[Decimal] = Decimal("0")
    ebay_fee: Optional[Decimal] = Decimal("0")
    purchase_cost: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    margin_percent: Optional[Decimal] = None


class OrderPurchase(BaseModel):
    amazon_purchase_url: Optional[str] = None
    purchase_cost: Decimal
    amazon_order_id: Optional[str] = Field(None, max_length=50)
    fulfillment_status: Optional[FulfillmentStatus] = None

    @field_validator("purchase_cost")
    @classmethod
    def purchase_cost_must_be_reasonable(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("purchase_cost must be non-negative")
        if v > 1_000_000:
            raise ValueError("purchase_cost must not exceed 1,000,000")
        return v


class OrderProfitDetailOut(BaseModel):
    order_id: int
    ebay_order_id: Optional[str] = None
    sale_price: Decimal
    shipping_cost: Optional[Decimal] = Decimal("0")
    ebay_fee: Optional[Decimal] = Decimal("0")
    purchase_cost: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    margin_percent: Optional[Decimal] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProfitSummaryOut(BaseModel):
    total_orders: int
    total_revenue: Decimal
    total_purchase_cost: Optional[Decimal] = None
    total_shipping_cost: Optional[Decimal] = None
    total_ebay_fees: Optional[Decimal] = None
    total_profit: Optional[Decimal] = None
    average_margin_percent: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseLinkOut(BaseModel):
    order_id: int
    purchase_url: Optional[str] = None


class OrderWebhookPayload(BaseModel):
    """Inbound eBay order webhook payload."""

    ebay_order_id: str
    buyer_username: Optional[str] = None
    sale_price: Decimal
    quantity: int = 1
    shipping_cost: Optional[Decimal] = Decimal("0")
    ebay_fee: Optional[Decimal] = Decimal("0")
    status: str = "pending"  # maps to OrderStatus
    sku: Optional[str] = None
    shipping_address: Optional[str] = None
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    raw_payload: Optional[str] = None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return v.lower()


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None


class OrderFulfillmentUpdate(BaseModel):
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    shipped_at: Optional[datetime] = None
    fulfillment_status: Optional[FulfillmentStatus] = Field(None, alias="status")


class PriceHistoryOut(BaseModel):
    id: int
    product_id: int
    price: Decimal
    currency: str
    source: str
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncLogOut(BaseModel):
    id: int
    sync_type: SyncType
    status: SyncStatus
    records_processed: int
    records_succeeded: int
    records_failed: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourcingRequest(BaseModel):
    keywords: Optional[List[str]] = None
    category: Optional[str] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    min_margin: Optional[float] = None
    max_results: int = 50
    auto_create_listings: bool = False


class SourcingResult(BaseModel):
    asin: str
    title: str
    amazon_price: Decimal
    estimated_ebay_price: Optional[Decimal] = None
    estimated_margin: Optional[float] = None
    category: Optional[str] = None
    image_url: Optional[str] = None


class PricingRuleBase(BaseModel):
    name: str = Field(..., max_length=200)
    rule_type: RuleType
    value: Decimal
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    min_margin_percent: Optional[Decimal] = None
    priority: int = 0
    is_active: bool = True


class PricingRuleCreate(PricingRuleBase):
    @field_validator("value")
    @classmethod
    def value_must_be_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("value must be non-negative")
        return v

    @model_validator(mode="after")
    def check_min_max_price(self):
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must be less than or equal to max_price")
        return self


class PricingRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    rule_type: Optional[RuleType] = None
    value: Optional[Decimal] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    min_margin_percent: Optional[Decimal] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("value")
    @classmethod
    def value_must_be_non_negative(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("value must be non-negative")
        return v

    @model_validator(mode="after")
    def check_min_max_price(self):
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must be less than or equal to max_price")
        return self


class PricingRuleOut(PricingRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PricingCalculateRequest(BaseModel):
    product_id: int


class PricingCalculateResponse(BaseModel):
    product_id: int
    amazon_price: Optional[Decimal] = None
    listing_price: Optional[Decimal] = None
    rule_applied: Optional[PricingRuleOut] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserBase(BaseModel):
    username: str = Field(..., max_length=100)
    email: str = Field(..., max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserOut(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"