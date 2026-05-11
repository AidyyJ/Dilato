import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.order_sync import (
    _sync_ebay_orders,
    sync_ebay_orders,
)
from app.models.models import (
    Listing,
    Order,
    OrderStatus,
    SyncStatus,
    SyncType,
)


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


def _make_mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_task_session():
    session = _make_mock_session()

    @asynccontextmanager
    async def _ctx():
        yield session

    with patch("app.tasks.order_sync.task_session", _ctx):
        yield session


@pytest.fixture
def mock_api():
    api = AsyncMock()
    api.close = AsyncMock()
    with patch("app.tasks.order_sync.EbayAPI", return_value=api):
        yield api


# ---------------------------------------------------------------------------
# _sync_ebay_orders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_ebay_orders_new_order(mock_task_session, mock_api):
    mock_api.get_orders.return_value = [
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
    # No existing order, no matched listing
    mock_task_session.execute.return_value = FakeResult([])

    result = await _sync_ebay_orders()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    added = [call.args[0] for call in mock_task_session.add.call_args_list]
    assert any(isinstance(a, Order) for a in added)
    order = [a for a in added if isinstance(a, Order)][0]
    assert order.ebay_order_id == "order-123"
    assert order.buyer_username == "buyer1"
    assert order.status.value == "pending"
    assert order.sale_price == Decimal("29.99")


@pytest.mark.asyncio
async def test_sync_ebay_orders_update_existing(mock_task_session, mock_api):
    existing = Order(
        id=10,
        ebay_order_id="order-123",
        buyer_username="oldbuyer",
        sale_price=Decimal("20.00"),
        quantity=1,
        status=OrderStatus.pending,
    )
    mock_api.get_orders.return_value = [
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
    mock_task_session.execute.return_value = FakeResult([existing])

    result = await _sync_ebay_orders()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert existing.buyer_username == "newbuyer"
    assert existing.status == OrderStatus.shipped
    assert existing.sale_price == Decimal("25.00")
    assert existing.quantity == 2


@pytest.mark.asyncio
async def test_sync_ebay_orders_cancelled(mock_task_session, mock_api):
    mock_api.get_orders.return_value = [
        {
            "orderId": "order-456",
            "buyer": {"username": "buyer2"},
            "orderFulfillmentStatus": "CANCELLED",
            "lineItems": [
                {
                    "lineItemCost": {"value": "10.00"},
                    "quantity": 1,
                    "sku": "SKU002",
                }
            ],
        }
    ]
    mock_task_session.execute.return_value = FakeResult([])

    result = await _sync_ebay_orders()
    assert result["succeeded"] == 1
    added = [call.args[0] for call in mock_task_session.add.call_args_list]
    order = [a for a in added if isinstance(a, Order)][0]
    assert order.status == OrderStatus.cancelled


@pytest.mark.asyncio
async def test_sync_ebay_orders_missing_line_items(mock_task_session, mock_api):
    mock_api.get_orders.return_value = [
        {
            "orderId": "order-789",
            "buyer": {"username": "buyer3"},
            "orderFulfillmentStatus": "NOT_STARTED",
            "lineItems": [],
        }
    ]
    mock_task_session.execute.return_value = FakeResult([])

    result = await _sync_ebay_orders()
    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1


@pytest.mark.asyncio
async def test_sync_ebay_orders_matched_listing(mock_task_session, mock_api):
    matched_listing = Listing(id=5, ebay_sku="SKU001", title="Matched")
    mock_api.get_orders.return_value = [
        {
            "orderId": "order-999",
            "buyer": {"username": "buyer4"},
            "orderFulfillmentStatus": "NOT_STARTED",
            "lineItems": [
                {
                    "lineItemCost": {"value": "15.00"},
                    "quantity": 1,
                    "sku": "SKU001",
                }
            ],
        }
    ]

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([])  # no existing order
        return FakeResult([matched_listing])  # matched listing

    mock_task_session.execute.side_effect = side_effect

    result = await _sync_ebay_orders()
    assert result["succeeded"] == 1
    added = [call.args[0] for call in mock_task_session.add.call_args_list]
    order = [a for a in added if isinstance(a, Order)][0]
    assert order.listing_id == 5


# ---------------------------------------------------------------------------
# Sync wrappers
# ---------------------------------------------------------------------------

def test_sync_ebay_orders_wrapper():
    with patch(
        "app.tasks.order_sync._sync_ebay_orders",
        new_callable=AsyncMock,
        return_value={"processed": 2},
    ) as mock_sync:
        result = sync_ebay_orders()
        assert result == {"processed": 2}
        mock_sync.assert_awaited_once()


def test_sync_ebay_orders_wrapper_retry():
    with patch.object(
        sync_ebay_orders, "retry", side_effect=Exception("retry called")
    ) as mock_retry:
        with patch(
            "app.tasks.order_sync.run_async",
            side_effect=Exception("fail"),
        ):
            with pytest.raises(Exception, match="retry called"):
                sync_ebay_orders()
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            countdown = kwargs.get("countdown")
            assert countdown is not None
            assert countdown != 60
            assert 0 < countdown <= 60
