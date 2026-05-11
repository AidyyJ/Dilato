import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import order_service
from app.models.models import Order, OrderStatus, Listing, ListingStatus, FulfillmentStatus
from app.schemas.schemas import (
    OrderWebhookPayload,
    OrderStatusUpdate,
    OrderFulfillmentUpdate,
    OrderUpdate,
    OrderPurchase,
)

_NOW = datetime.now(timezone.utc)


class FakeScalarResult:
    def __init__(self, data):
        self._data = data

    def all(self):
        return self._data


class FakeResult:
    def __init__(self, data):
        self._data = data

    def scalars(self):
        return FakeScalarResult(self._data)

    def scalar_one_or_none(self):
        return self._data[0] if self._data else None


def _make_mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_order_found():
    db = _make_mock_db()
    order = Order(id=1, ebay_order_id="order-1", sale_price=Decimal("10.00"), status=OrderStatus.pending)
    db.execute.return_value = FakeResult([order])
    result = await order_service.get_order(db, 1)
    assert result == order


@pytest.mark.asyncio
async def test_get_order_not_found():
    db = _make_mock_db()
    db.execute.return_value = FakeResult([])
    result = await order_service.get_order(db, 99)
    assert result is None


# ---------------------------------------------------------------------------
# list_orders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_orders_no_filter():
    db = _make_mock_db()
    orders = [
        Order(id=1, ebay_order_id="o1", sale_price=Decimal("10.00"), status=OrderStatus.pending),
        Order(id=2, ebay_order_id="o2", sale_price=Decimal("20.00"), status=OrderStatus.shipped),
    ]
    db.execute.return_value = FakeResult(orders)
    result = await order_service.list_orders(db)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_orders_filter_by_status():
    db = _make_mock_db()
    orders = [
        Order(id=1, ebay_order_id="o1", sale_price=Decimal("10.00"), status=OrderStatus.pending),
    ]
    db.execute.return_value = FakeResult(orders)
    result = await order_service.list_orders(db, status=OrderStatus.pending)
    assert len(result) == 1
    assert result[0].status == OrderStatus.pending


# ---------------------------------------------------------------------------
# process_order_webhook — create new
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_webhook_create_new():
    db = _make_mock_db()
    db.execute.return_value = FakeResult([])  # no existing order

    payload = OrderWebhookPayload(
        ebay_order_id="order-123",
        buyer_username="buyer1",
        sale_price=Decimal("29.99"),
        quantity=1,
        status="pending",
    )

    result = await order_service.process_order_webhook(db, payload)
    assert result.ebay_order_id == "order-123"
    assert result.buyer_username == "buyer1"
    assert result.status == OrderStatus.pending
    assert result.sale_price == Decimal("29.99")
    db.add.assert_called_once()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_webhook_create_with_sku_links_listing():
    db = _make_mock_db()
    listing = Listing(id=5, ebay_sku="SKU001", title="Test", quantity=10, quantity_sold=2, status=ListingStatus.active)

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([])  # no existing order
        return FakeResult([listing])  # matched listing

    db.execute.side_effect = side_effect

    payload = OrderWebhookPayload(
        ebay_order_id="order-456",
        buyer_username="buyer2",
        sale_price=Decimal("15.00"),
        quantity=3,
        sku="SKU001",
        status="pending",
    )

    result = await order_service.process_order_webhook(db, payload)
    assert result.listing_id == 5
    assert listing.quantity_sold == 5  # 2 + 3
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_webhook_create_with_sku_marks_sold():
    db = _make_mock_db()
    listing = Listing(id=6, ebay_sku="SKU002", title="Test", quantity=5, quantity_sold=3, status=ListingStatus.active)

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([])
        return FakeResult([listing])

    db.execute.side_effect = side_effect

    payload = OrderWebhookPayload(
        ebay_order_id="order-789",
        buyer_username="buyer3",
        sale_price=Decimal("10.00"),
        quantity=2,
        sku="SKU002",
        status="pending",
    )

    result = await order_service.process_order_webhook(db, payload)
    assert listing.quantity_sold == 5
    assert listing.status == ListingStatus.sold


# ---------------------------------------------------------------------------
# process_order_webhook — update existing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_webhook_update_existing():
    db = _make_mock_db()
    existing = Order(
        id=10,
        ebay_order_id="order-123",
        buyer_username="oldbuyer",
        sale_price=Decimal("20.00"),
        quantity=1,
        status=OrderStatus.pending,
    )
    db.execute.return_value = FakeResult([existing])

    payload = OrderWebhookPayload(
        ebay_order_id="order-123",
        buyer_username="newbuyer",
        sale_price=Decimal("25.00"),
        quantity=2,
        status="shipped",
    )

    result = await order_service.process_order_webhook(db, payload)
    assert result.buyer_username == "newbuyer"
    assert result.sale_price == Decimal("25.00")
    assert result.quantity == 2
    assert result.status == OrderStatus.shipped
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_webhook_unknown_status_defaults_to_pending():
    db = _make_mock_db()
    db.execute.return_value = FakeResult([])

    payload = OrderWebhookPayload(
        ebay_order_id="order-abc",
        sale_price=Decimal("5.00"),
        status="UNKNOWN_STATUS",
    )

    result = await order_service.process_order_webhook(db, payload)
    assert result.status == OrderStatus.pending


# ---------------------------------------------------------------------------
# update_order_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_order_status():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("10.00"),
        status=OrderStatus.pending,
    )
    update = OrderStatusUpdate(status=OrderStatus.shipped, shipped_at=_NOW)
    result = await order_service.update_order_status(db, order, update)
    assert result.status == OrderStatus.shipped
    assert result.shipped_at == _NOW
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# update_order_fulfillment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_order_fulfillment():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("10.00"),
        status=OrderStatus.pending,
    )
    update = OrderFulfillmentUpdate(
        tracking_number="TRACK123",
        carrier="UPS",
        shipped_at=_NOW,
        fulfillment_status=FulfillmentStatus.in_progress,
    )
    result = await order_service.update_order_fulfillment(db, order, update)
    assert result.tracking_number == "TRACK123"
    assert result.carrier == "UPS"
    assert result.shipped_at == _NOW
    assert result.fulfillment_status == FulfillmentStatus.in_progress
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# calculate_profit
# ---------------------------------------------------------------------------

def test_calculate_profit_with_all_costs():
    profit, margin = order_service.calculate_profit(
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        purchase_cost=Decimal("60.00"),
    )
    assert profit == Decimal("35.00")
    assert margin == Decimal("33.33")


def test_calculate_profit_no_purchase_cost():
    profit, margin = order_service.calculate_profit(
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        purchase_cost=None,
    )
    assert profit is None
    assert margin is None


def test_calculate_profit_defaults():
    profit, margin = order_service.calculate_profit(
        sale_price=Decimal("100.00"),
        purchase_cost=Decimal("80.00"),
    )
    assert profit == Decimal("20.00")
    assert margin == Decimal("20.00")


# ---------------------------------------------------------------------------
# update_order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_order_purchase_cost_triggers_profit():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        status=OrderStatus.pending,
    )
    update = OrderUpdate(purchase_cost=Decimal("60.00"), amazon_order_id="AMZ-123")
    result = await order_service.update_order(db, order, update)
    assert result.purchase_cost == Decimal("60.00")
    assert result.amazon_order_id == "AMZ-123"
    assert result.profit == Decimal("35.00")
    assert result.margin_percent == Decimal("33.33")
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_order_clear_purchase_cost_clears_profit():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        purchase_cost=Decimal("60.00"),
        profit=Decimal("35.00"),
        margin_percent=Decimal("33.33"),
        status=OrderStatus.pending,
    )
    update = OrderUpdate(purchase_cost=None)
    result = await order_service.update_order(db, order, update)
    assert result.purchase_cost is None
    assert result.profit is None
    assert result.margin_percent is None
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# sync_orders_from_ebay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_orders_from_ebay_new_order():
    db = _make_mock_db()
    api = AsyncMock()
    api.get_orders.return_value = [
        {
            "orderId": "order-123",
            "buyer": {"username": "buyer1"},
            "orderFulfillmentStatus": "NOT_STARTED",
            "lineItems": [
                {
                    "lineItemCost": {"value": "29.99"},
                    "quantity": 1,
                    "sku": "SKU001",
                }
            ],
        }
    ]
    db.execute.return_value = FakeResult([])

    result = await order_service.sync_orders_from_ebay(db, api)
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    db.commit.assert_awaited()
    api.get_orders.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_orders_from_ebay_update_existing():
    db = _make_mock_db()
    existing = Order(
        id=10,
        ebay_order_id="order-123",
        buyer_username="oldbuyer",
        sale_price=Decimal("20.00"),
        quantity=1,
        status=OrderStatus.pending,
    )
    api = AsyncMock()
    api.get_orders.return_value = [
        {
            "orderId": "order-123",
            "buyer": {"username": "newbuyer"},
            "orderFulfillmentStatus": "FULFILLED",
            "lineItems": [
                {
                    "lineItemCost": {"value": "25.00"},
                    "quantity": 2,
                    "sku": "SKU001",
                }
            ],
        }
    ]
    db.execute.return_value = FakeResult([existing])

    result = await order_service.sync_orders_from_ebay(db, api)
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert existing.buyer_username == "newbuyer"
    assert existing.status == OrderStatus.shipped
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# record_purchase
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_purchase_sets_fields_and_calculates_profit():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        status=OrderStatus.pending,
    )
    purchase = OrderPurchase(
        purchase_cost=Decimal("60.00"),
        amazon_order_id="AMZ-123",
        amazon_purchase_url="https://amazon.com/order/123",
        fulfillment_status=FulfillmentStatus.not_started,
    )
    result = await order_service.record_purchase(db, order, purchase)
    assert result.purchase_cost == Decimal("60.00")
    assert result.amazon_order_id == "AMZ-123"
    assert result.amazon_purchase_url == "https://amazon.com/order/123"
    assert result.fulfillment_status == FulfillmentStatus.not_started
    assert result.purchased_at is not None
    assert result.profit == Decimal("35.00")
    assert result.margin_percent == Decimal("33.33")
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_record_purchase_zero_purchase_cost():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        status=OrderStatus.pending,
    )
    purchase = OrderPurchase(purchase_cost=Decimal("0.00"))
    result = await order_service.record_purchase(db, order, purchase)
    assert result.profit == Decimal("95.00")
    assert result.margin_percent == Decimal("90.48")



