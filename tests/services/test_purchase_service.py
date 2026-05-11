import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.services import purchase_service, order_service
from app.models.models import Order, OrderStatus, Listing, Product, FulfillmentStatus
from app.schemas.schemas import OrderPurchase


def _make_mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# generate_amazon_purchase_link
# ---------------------------------------------------------------------------

def test_generate_purchase_link_with_asin():
    product = Product(id=1, asin="B08N5WRWNW", title="Test Product")
    listing = Listing(id=1, product_id=1, title="Test", quantity=10)
    listing.product = product
    order = Order(id=1, listing_id=1, quantity=2)
    order.listing = listing
    link = purchase_service.generate_amazon_purchase_link(order)
    assert "amazon.com" in link
    assert "B08N5WRWNW" in link
    assert "Quantity.1=2" in link


def test_generate_purchase_link_no_listing():
    order = Order(id=1, quantity=1)
    order.listing = None
    link = purchase_service.generate_amazon_purchase_link(order)
    assert link is None


def test_generate_purchase_link_no_product():
    listing = Listing(id=1, title="Test", quantity=10)
    listing.product = None
    order = Order(id=1, listing_id=1, quantity=1)
    order.listing = listing
    link = purchase_service.generate_amazon_purchase_link(order)
    assert link is None


def test_generate_purchase_link_no_asin():
    product = Product(id=1, asin="", title="Test Product")
    listing = Listing(id=1, product_id=1, title="Test", quantity=10)
    listing.product = product
    order = Order(id=1, listing_id=1, quantity=1)
    order.listing = listing
    link = purchase_service.generate_amazon_purchase_link(order)
    assert link is None


# ---------------------------------------------------------------------------
# mark_order_purchased
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_order_purchased_success():
    db = _make_mock_db()
    product = Product(id=1, asin="B08N5WRWNW", title="Test Product")
    listing = Listing(id=1, product_id=1, title="Test", quantity=10)
    listing.product = product
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        status=OrderStatus.pending,
        quantity=1,
    )
    order.listing = listing

    db.execute.return_value = type("R", (), {"scalar_one_or_none": lambda self: order})()

    result = await purchase_service.mark_order_purchased(
        db,
        order_id=1,
        amazon_order_id="AMZ-123",
        purchase_cost=Decimal("60.00"),
        fulfillment_status=FulfillmentStatus.not_started,
    )
    assert result is not None
    assert result.purchase_cost == Decimal("60.00")
    assert result.amazon_order_id == "AMZ-123"
    assert result.purchased_at is not None
    assert result.profit == Decimal("35.00")
    assert result.margin_percent == Decimal("33.33")
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_mark_order_purchased_not_found():
    db = _make_mock_db()
    db.execute.return_value = type("R", (), {"scalar_one_or_none": lambda self: None})()

    result = await purchase_service.mark_order_purchased(
        db,
        order_id=99,
        purchase_cost=Decimal("60.00"),
    )
    assert result is None
