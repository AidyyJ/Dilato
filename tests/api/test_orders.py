import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.models import Order, OrderStatus, FulfillmentStatus, Listing, ListingStatus

_NOW = datetime.now(timezone.utc)


def _make_order(**overrides) -> Order:
    """Build a complete Order instance with sensible defaults for testing."""
    defaults = dict(
        id=1,
        ebay_order_id="order-123",
        buyer_username="buyer1",
        sale_price=Decimal("29.99"),
        quantity=1,
        shipping_cost=Decimal("0"),
        ebay_fee=Decimal("0"),
        status=OrderStatus.pending,
        fulfillment_status=FulfillmentStatus.not_started,
        listing_id=None,
        amazon_purchase_url=None,
        purchase_cost=None,
        profit=None,
        margin_percent=None,
        amazon_order_id=None,
        purchased_at=None,
        tracking_number=None,
        carrier=None,
        payment_status=None,
        shipping_address=None,
        raw_payload=None,
        last_webhook_at=None,
        shipped_at=None,
        delivered_at=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(overrides)
    return Order(**defaults)


pytestmark = pytest.mark.usefixtures("override_auth")


# ---------------------------------------------------------------------------
# GET /api/v1/orders/{order_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_order_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get("/api/v1/orders/99")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_order_success(client):
    order = _make_order(id=1, ebay_order_id="order-123", buyer_username="buyer1", sale_price=Decimal("29.99"), status=OrderStatus.pending)
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=order,
    ):
        response = await client.get("/api/v1/orders/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["ebay_order_id"] == "order-123"
        assert data["status"] == "pending"


# ---------------------------------------------------------------------------
# GET /api/v1/orders/
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_orders(client):
    orders = [
        _make_order(id=1, ebay_order_id="o1", sale_price=Decimal("10.00"), status=OrderStatus.pending),
    ]
    with patch(
        "app.api.v1.endpoints.orders.order_service.list_orders",
        new_callable=AsyncMock,
        return_value=orders,
    ):
        response = await client.get("/api/v1/orders/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ebay_order_id"] == "o1"


# ---------------------------------------------------------------------------
# POST /api/v1/orders/webhook (no auth)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_webhook_create(client):
    order = _make_order(id=1, ebay_order_id="order-123", buyer_username="buyer1", sale_price=Decimal("29.99"), status=OrderStatus.pending)
    with patch(
        "app.api.v1.endpoints.orders.order_service.process_order_webhook",
        new_callable=AsyncMock,
        return_value=order,
    ) as mock_process:
        response = await client.post(
            "/api/v1/orders/webhook",
            json={
                "ebay_order_id": "order-123",
                "buyer_username": "buyer1",
                "sale_price": "29.99",
                "quantity": 1,
                "status": "pending",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["ebay_order_id"] == "order-123"
        mock_process.assert_awaited_once()


# ---------------------------------------------------------------------------
# PATCH /api/v1/orders/{order_id}/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_order_status(client):
    order = _make_order(id=1, ebay_order_id="order-1", sale_price=Decimal("10.00"), status=OrderStatus.shipped, shipped_at=_NOW)
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=order,
    ), patch(
        "app.api.v1.endpoints.orders.order_service.update_order_status",
        new_callable=AsyncMock,
        return_value=order,
    ) as mock_update:
        response = await client.patch(
            "/api/v1/orders/1/status",
            json={"status": "shipped", "shipped_at": _NOW.isoformat()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shipped"
        mock_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_order_status_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.patch(
            "/api/v1/orders/99/status",
            json={"status": "shipped"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/orders/{order_id}/fulfillment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_order_fulfillment(client):
    order = _make_order(id=1, ebay_order_id="order-1", sale_price=Decimal("10.00"), status=OrderStatus.shipped, tracking_number="TRACK123", carrier="UPS")
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=order,
    ), patch(
        "app.api.v1.endpoints.orders.order_service.update_order_fulfillment",
        new_callable=AsyncMock,
        return_value=order,
    ) as mock_update:
        response = await client.patch(
            "/api/v1/orders/1/fulfillment",
            json={"tracking_number": "TRACK123", "carrier": "UPS"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tracking_number"] == "TRACK123"
        assert data["carrier"] == "UPS"
        mock_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_order_fulfillment_status(client):
    order = _make_order(id=1, ebay_order_id="order-1", sale_price=Decimal("10.00"), status=OrderStatus.pending)
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=order,
    ), patch(
        "app.api.v1.endpoints.orders.order_service.update_order_fulfillment",
        new_callable=AsyncMock,
        return_value=order,
    ) as mock_update:
        response = await client.patch(
            "/api/v1/orders/1/fulfillment",
            json={"status": "in_progress"},
        )
        assert response.status_code == 200
        mock_update.assert_awaited_once()
        call_args = mock_update.call_args[0][2]
        assert call_args.fulfillment_status.value == "in_progress"


@pytest.mark.asyncio
async def test_update_order_fulfillment_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.patch(
            "/api/v1/orders/99/fulfillment",
            json={"tracking_number": "TRACK123"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/orders/{order_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_order(client):
    order = _make_order(id=1, ebay_order_id="order-1", sale_price=Decimal("100.00"), status=OrderStatus.pending)
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=order,
    ), patch(
        "app.api.v1.endpoints.orders.order_service.update_order",
        new_callable=AsyncMock,
        return_value=order,
    ) as mock_update:
        response = await client.patch(
            "/api/v1/orders/1",
            json={
                "status": "shipped",
                "amazon_purchase_url": "https://amazon.com/order/123",
                "purchase_cost": "60.00",
                "amazon_order_id": "AMZ-123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        mock_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_order_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.patch(
            "/api/v1/orders/99",
            json={"status": "shipped"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/orders/{order_id}/purchase-link
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purchase_link(client):
    order = _make_order(id=1, ebay_order_id="order-1", sale_price=Decimal("100.00"), status=OrderStatus.pending)
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order_with_product",
        new_callable=AsyncMock,
        return_value=order,
    ), patch(
        "app.api.v1.endpoints.orders.purchase_service.generate_amazon_purchase_link",
        return_value="https://www.amazon.com/gp/aws/cart/add.html?ASIN.1=B08N5WRWNW&Quantity.1=1",
    ):
        response = await client.post("/api/v1/orders/1/purchase-link")
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == 1
        assert "amazon.com" in data["purchase_url"]


@pytest.mark.asyncio
async def test_purchase_link_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.order_service.get_order_with_product",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post("/api/v1/orders/99/purchase-link")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/orders/{order_id}/mark-purchased
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_purchased(client):
    order = _make_order(id=1, ebay_order_id="order-1", sale_price=Decimal("100.00"), shipping_cost=Decimal("5.00"), ebay_fee=Decimal("10.00"), status=OrderStatus.pending)
    with patch(
        "app.api.v1.endpoints.orders.purchase_service.mark_order_purchased",
        new_callable=AsyncMock,
        return_value=order,
    ) as mock_mark:
        response = await client.post(
            "/api/v1/orders/1/mark-purchased",
            json={
                "purchase_cost": "60.00",
                "amazon_order_id": "AMZ-123",
                "amazon_purchase_url": "https://amazon.com/order/123",
            },
        )
        assert response.status_code == 200
        mock_mark.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_purchased_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.purchase_service.mark_order_purchased",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post(
            "/api/v1/orders/99/mark-purchased",
            json={"purchase_cost": "60.00"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/orders/{order_id}/profit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_order_profit(client):
    profit_detail = {
        "order_id": 1,
        "ebay_order_id": "order-1",
        "sale_price": "100.00",
        "shipping_cost": "5.00",
        "ebay_fee": "10.00",
        "purchase_cost": "60.00",
        "profit": "35.00",
        "margin_percent": "33.33",
    }
    with patch(
        "app.api.v1.endpoints.orders.profit_service.calculate_order_profit",
        new_callable=AsyncMock,
        return_value=profit_detail,
    ) as mock_profit:
        response = await client.get("/api/v1/orders/1/profit")
        assert response.status_code == 200
        data = response.json()
        assert data["profit"] == "35.00"
        assert data["margin_percent"] == "33.33"
        mock_profit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_order_profit_not_found(client):
    with patch(
        "app.api.v1.endpoints.orders.profit_service.calculate_order_profit",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get("/api/v1/orders/99/profit")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/orders/profit/summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_profit_summary(client):
    summary = {
        "total_orders": 5,
        "total_revenue": "500.00",
        "total_purchase_cost": "300.00",
        "total_shipping_cost": "25.00",
        "total_ebay_fees": "50.00",
        "total_profit": "125.00",
        "average_margin_percent": "25.00",
    }
    with patch(
        "app.api.v1.endpoints.orders.profit_service.get_profit_summary",
        new_callable=AsyncMock,
        return_value=summary,
    ) as mock_summary:
        response = await client.get("/api/v1/orders/profit/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_orders"] == 5
        assert data["total_profit"] == "125.00"
        mock_summary.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /api/v1/orders/profit/details
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_profit_details(client):
    details = [
        {
            "order_id": 1,
            "ebay_order_id": "order-1",
            "sale_price": "100.00",
            "shipping_cost": "5.00",
            "ebay_fee": "10.00",
            "purchase_cost": "60.00",
            "profit": "35.00",
            "margin_percent": "33.33",
        }
    ]
    with patch(
        "app.api.v1.endpoints.orders.profit_service.get_profit_details",
        new_callable=AsyncMock,
        return_value=details,
    ) as mock_details:
        response = await client.get("/api/v1/orders/profit/details")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["profit"] == "35.00"
        mock_details.assert_awaited_once()
