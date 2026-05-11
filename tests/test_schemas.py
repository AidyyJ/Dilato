import pytest
from decimal import Decimal
from pydantic import ValidationError

from app.schemas.schemas import ProductCreate, ListingCreate, OrderPurchase


def test_product_create_rejects_javascript_url():
    with pytest.raises(ValidationError, match="URL must use http or https scheme"):
        ProductCreate(
            asin="B123",
            title="Test",
            detail_page_url="javascript:alert('xss')",
        )


def test_product_create_rejects_data_url():
    with pytest.raises(ValidationError, match="URL must use http or https scheme"):
        ProductCreate(
            asin="B123",
            title="Test",
            image_url="data:text/html,<script>alert('xss')</script>",
        )


def test_product_create_allows_https_url():
    product = ProductCreate(
        asin="B123",
        title="Test",
        detail_page_url="https://amazon.com/dp/B123",
        image_url="https://example.com/img.jpg",
    )
    assert product.detail_page_url == "https://amazon.com/dp/B123"
    assert product.image_url == "https://example.com/img.jpg"


def test_product_create_allows_none_urls():
    product = ProductCreate(
        asin="B123",
        title="Test",
        detail_page_url=None,
        image_url=None,
    )
    assert product.detail_page_url is None
    assert product.image_url is None


# ---------------------------------------------------------------------------
# ListingCreate validators
# ---------------------------------------------------------------------------


def test_listing_create_rejects_non_positive_price():
    with pytest.raises(ValidationError, match="listing_price must be greater than 0"):
        ListingCreate(product_id=1, title="Test", listing_price=Decimal("0"))


def test_listing_create_rejects_negative_price():
    with pytest.raises(ValidationError, match="listing_price must be greater than 0"):
        ListingCreate(product_id=1, title="Test", listing_price=Decimal("-5.00"))


def test_listing_create_rejects_zero_quantity():
    with pytest.raises(ValidationError, match="quantity must be greater than 0"):
        ListingCreate(product_id=1, title="Test", listing_price=Decimal("10.00"), quantity=0)


def test_listing_create_rejects_negative_quantity():
    with pytest.raises(ValidationError, match="quantity must be greater than 0"):
        ListingCreate(product_id=1, title="Test", listing_price=Decimal("10.00"), quantity=-1)


def test_listing_create_allows_none_price():
    listing = ListingCreate(product_id=1, title="Test")
    assert listing.listing_price is None


def test_listing_create_allows_default_quantity():
    listing = ListingCreate(product_id=1, title="Test", listing_price=Decimal("10.00"))
    assert listing.quantity == 1


# ---------------------------------------------------------------------------
# OrderPurchase validators
# ---------------------------------------------------------------------------


def test_order_purchase_rejects_negative_cost():
    with pytest.raises(ValidationError, match="purchase_cost must be non-negative"):
        OrderPurchase(purchase_cost=Decimal("-1.00"))


def test_order_purchase_rejects_excessive_cost():
    with pytest.raises(ValidationError, match="purchase_cost must not exceed 1,000,000"):
        OrderPurchase(purchase_cost=Decimal("2000000.00"))


def test_order_purchase_allows_zero_cost():
    purchase = OrderPurchase(purchase_cost=Decimal("0.00"))
    assert purchase.purchase_cost == Decimal("0.00")
