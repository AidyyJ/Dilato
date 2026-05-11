import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx

from app.services.ebay_api import EbayAPI, EbayAPIError


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(
        "app.services.ebay_api.settings.EBAY_CLIENT_ID", "test-client-id"
    )
    monkeypatch.setattr(
        "app.services.ebay_api.settings.EBAY_CLIENT_SECRET", "test-client-secret"
    )
    monkeypatch.setattr("app.services.ebay_api.settings.EBAY_DEV_ID", "test-dev-id")
    monkeypatch.setattr(
        "app.services.ebay_api.settings.EBAY_RU_NAME", "test-ru-name"
    )
    monkeypatch.setattr("app.services.ebay_api.settings.EBAY_SITE_ID", 0)
    monkeypatch.setattr(
        "app.services.ebay_api.settings.EBAY_API_BASE_URL", "https://api.ebay.com"
    )
    instance = EbayAPI()
    instance._client = AsyncMock()
    instance._access_token = "test-token"
    instance._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return instance


# ---------------------------------------------------------------------------
# OAuth / Token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_token_returns_cached(api):
    token = await api._ensure_token()
    assert token == "test-token"
    api._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_token_success(api):
    api._access_token = None
    api._token_expires_at = None
    api._client.post.return_value = FakeResponse(
        200, {"access_token": "new-token", "expires_in": 7200}
    )
    token = await api._refresh_token()
    assert token == "new-token"
    assert api._access_token == "new-token"
    api._client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_token_error(api):
    api._access_token = None
    api._token_expires_at = None
    api._client.post.return_value = FakeResponse(
        400,
        {
            "error": "invalid_client",
            "error_description": "Client credentials are invalid",
        },
    )
    with pytest.raises(EbayAPIError, match="Client credentials are invalid"):
        await api._refresh_token()


@pytest.mark.asyncio
async def test_refresh_token_network_error(api):
    api._access_token = None
    api._token_expires_at = None
    api._client.post.side_effect = httpx.ConnectError("Connection failed")
    with pytest.raises(EbayAPIError, match="Connection failed"):
        await api._refresh_token()


@pytest.mark.asyncio
async def test_missing_credentials(monkeypatch):
    monkeypatch.setattr("app.services.ebay_api.settings.EBAY_CLIENT_ID", "")
    monkeypatch.setattr("app.services.ebay_api.settings.EBAY_CLIENT_SECRET", "")
    bad_api = EbayAPI()
    bad_api._client = AsyncMock()
    with pytest.raises(EbayAPIError, match="credentials are not configured"):
        await bad_api._refresh_token()


# ---------------------------------------------------------------------------
# Request wrapper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_success(api):
    api._client.request.return_value = FakeResponse(200, {"data": "value"})
    result = await api._request("GET", "/test/path")
    assert result == {"data": "value"}
    _, kwargs = api._client.request.call_args
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert kwargs["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"


@pytest.mark.asyncio
async def test_request_error(api):
    api._client.request.return_value = FakeResponse(
        400, {"errors": [{"errorId": 123, "message": "Bad request"}]}
    )
    with pytest.raises(EbayAPIError, match="Bad request"):
        await api._request("GET", "/test/path")


@pytest.mark.asyncio
async def test_request_502_error(api):
    api._client.request.return_value = FakeResponse(
        502, {"errors": [{"errorId": 999, "message": "Bad Gateway"}]}
    )
    with pytest.raises(EbayAPIError, match="Bad Gateway"):
        await api._request("GET", "/test/path")


@pytest.mark.asyncio
async def test_request_422_error(api):
    api._client.request.return_value = FakeResponse(
        422, {"errors": [{"errorId": 2001, "message": "Invalid data"}]}
    )
    with pytest.raises(EbayAPIError, match="Invalid data"):
        await api._request("POST", "/test/path", json_data={"bad": "data"})


@pytest.mark.asyncio
async def test_request_network_error(api):
    api._client.request.side_effect = httpx.ConnectError("Connection failed")
    with pytest.raises(EbayAPIError, match="Connection failed"):
        await api._request("GET", "/test/path")


@pytest.mark.asyncio
async def test_request_204_returns_empty(api):
    api._client.request.return_value = FakeResponse(204, {})
    result = await api._request("DELETE", "/test/path")
    assert result == {}


# ---------------------------------------------------------------------------
# Inventory items
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_or_update_inventory_item(api):
    api._client.request.return_value = FakeResponse(204, {})
    result = await api.create_or_update_inventory_item(
        "SKU001", {"product": {"title": "Test"}}
    )
    assert result == {}
    _, kwargs = api._client.request.call_args
    assert kwargs["method"] == "PUT"
    assert "/inventory_item/SKU001" in kwargs["url"]


@pytest.mark.asyncio
async def test_get_inventory_item_success(api):
    api._client.request.return_value = FakeResponse(
        200, {"sku": "SKU001", "product": {"title": "Test Product"}}
    )
    result = await api.get_inventory_item("SKU001")
    assert result is not None
    assert result["sku"] == "SKU001"


@pytest.mark.asyncio
async def test_get_inventory_item_not_found(api):
    api._client.request.return_value = FakeResponse(
        400,
        {"errors": [{"errorId": 25810, "message": "Inventory item does not exist"}]},
    )
    result = await api.get_inventory_item("SKU001")
    assert result is None


@pytest.mark.asyncio
async def test_delete_inventory_item(api):
    api._client.request.return_value = FakeResponse(204, {})
    await api.delete_inventory_item("SKU001")
    _, kwargs = api._client.request.call_args
    assert kwargs["method"] == "DELETE"


# ---------------------------------------------------------------------------
# Offers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_offer(api):
    api._client.request.return_value = FakeResponse(201, {"offerId": "offer123"})
    result = await api.create_offer({"sku": "SKU001", "marketplaceId": "EBAY_US"})
    assert result["offerId"] == "offer123"


@pytest.mark.asyncio
async def test_get_offer_success(api):
    api._client.request.return_value = FakeResponse(
        200, {"offerId": "offer123", "sku": "SKU001"}
    )
    result = await api.get_offer("offer123")
    assert result is not None
    assert result["offerId"] == "offer123"


@pytest.mark.asyncio
async def test_get_offer_not_found(api):
    api._client.request.return_value = FakeResponse(
        400,
        {"errors": [{"errorId": 25002, "message": "Offer does not exist"}]},
    )
    result = await api.get_offer("offer123")
    assert result is None


@pytest.mark.asyncio
async def test_get_offers(api):
    api._client.request.return_value = FakeResponse(
        200, {"offers": [{"offerId": "o1"}, {"offerId": "o2"}], "total": 2}
    )
    result = await api.get_offers()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_find_offer_by_sku(api):
    api._client.request.return_value = FakeResponse(
        200,
        {
            "offers": [
                {"offerId": "o1", "sku": "SKU001"},
                {"offerId": "o2", "sku": "SKU002"},
            ],
            "total": 2,
        },
    )
    result = await api._find_offer_by_sku("SKU002")
    assert result is not None
    assert result["offerId"] == "o2"


@pytest.mark.asyncio
async def test_find_offer_by_sku_not_found(api):
    api._client.request.return_value = FakeResponse(
        200, {"offers": [], "total": 0}
    )
    result = await api._find_offer_by_sku("SKU999")
    assert result is None


@pytest.mark.asyncio
async def test_update_offer(api):
    api._client.request.return_value = FakeResponse(204, {})
    result = await api.update_offer("offer123", {"availableQuantity": 5})
    _, kwargs = api._client.request.call_args
    assert kwargs["method"] == "PUT"


@pytest.mark.asyncio
async def test_publish_offer(api):
    api._client.request.return_value = FakeResponse(
        200, {"listingId": "123456789"}
    )
    result = await api.publish_offer("offer123")
    assert result["listingId"] == "123456789"


@pytest.mark.asyncio
async def test_withdraw_offer(api):
    api._client.request.return_value = FakeResponse(200, {})
    result = await api.withdraw_offer("offer123")
    assert result == {}


# ---------------------------------------------------------------------------
# High-level listing CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_listing_success(api):
    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = kwargs.get("url", "")
        method = kwargs.get("method", "")
        if "/inventory_item/" in url and method == "PUT":
            return FakeResponse(204, {})
        if url.endswith("/offer") and method == "POST":
            return FakeResponse(201, {"offerId": "offer123"})
        if "/publish" in url:
            return FakeResponse(200, {"listingId": "987654321"})
        return FakeResponse(200, {})

    api._client.request.side_effect = mock_request

    result = await api.create_listing(
        {
            "sku": "SKU001",
            "title": "Test Product",
            "description": "A great product",
            "price": "29.99",
            "quantity": 5,
            "category_id": "1234",
        }
    )
    assert result["sku"] == "SKU001"
    assert result["offer_id"] == "offer123"
    assert result["item_id"] == "987654321"
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_create_listing_missing_sku(api):
    with pytest.raises(EbayAPIError, match="sku is required"):
        await api.create_listing({"title": "Test", "price": "10.00"})


@pytest.mark.asyncio
async def test_create_listing_missing_price(api):
    with pytest.raises(EbayAPIError, match="price is required"):
        await api.create_listing({"sku": "SKU001", "title": "Test"})


@pytest.mark.asyncio
async def test_get_listing_success(api):
    api._client.request.return_value = FakeResponse(
        200, {"sku": "SKU001", "product": {"title": "Test Product"}}
    )
    result = await api.get_listing("SKU001")
    assert result is not None
    assert result["sku"] == "SKU001"
    assert result["inventory_item"]["product"]["title"] == "Test Product"


@pytest.mark.asyncio
async def test_get_listing_not_found(api):
    api._client.request.return_value = FakeResponse(
        400,
        {"errors": [{"errorId": 25810, "message": "Inventory item does not exist"}]},
    )
    result = await api.get_listing("SKU001")
    assert result is None


@pytest.mark.asyncio
async def test_update_listing_success(api):
    async def mock_request(*args, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method", "")
        if "/inventory_item/SKU001" in url and method == "GET":
            return FakeResponse(
                200,
                {
                    "sku": "SKU001",
                    "product": {"title": "Old Title", "description": "Old Desc"},
                    "availability": {
                        "shipToLocationAvailability": {"quantity": 3}
                    },
                    "condition": "NEW",
                },
            )
        if "/inventory_item/SKU001" in url and method == "PUT":
            return FakeResponse(204, {})
        if "/offer/offer123" in url and method == "GET":
            return FakeResponse(
                200,
                {
                    "offerId": "offer123",
                    "pricingSummary": {
                        "price": {"value": "10.00", "currency": "USD"}
                    },
                    "availableQuantity": 3,
                },
            )
        if "/offer/offer123" in url and method == "PUT":
            return FakeResponse(204, {})
        return FakeResponse(200, {})

    api._client.request.side_effect = mock_request

    result = await api.update_listing(
        "SKU001",
        {
            "title": "New Title",
            "price": "15.99",
            "quantity": 10,
            "offer_id": "offer123",
        },
    )
    assert result["sku"] == "SKU001"
    assert result["updated"] is True


@pytest.mark.asyncio
async def test_update_listing_item_not_found(api):
    api._client.request.return_value = FakeResponse(
        400,
        {"errors": [{"errorId": 25810, "message": "Inventory item does not exist"}]},
    )
    with pytest.raises(EbayAPIError, match="not found for SKU"):
        await api.update_listing("SKU001", {"title": "New"})


@pytest.mark.asyncio
async def test_update_listing_auto_resolve_offer_id(api):
    async def mock_request(*args, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method", "")
        if "/inventory_item/SKU001" in url and method == "GET":
            return FakeResponse(
                200,
                {
                    "sku": "SKU001",
                    "product": {"title": "Old Title", "description": "Old Desc"},
                    "availability": {
                        "shipToLocationAvailability": {"quantity": 3}
                    },
                    "condition": "NEW",
                },
            )
        if "/inventory_item/SKU001" in url and method == "PUT":
            return FakeResponse(204, {})
        if "/offer" in url and method == "GET":
            return FakeResponse(
                200,
                {
                    "offers": [
                        {
                            "offerId": "offer123",
                            "sku": "SKU001",
                            "pricingSummary": {
                                "price": {"value": "10.00", "currency": "USD"}
                            },
                            "availableQuantity": 3,
                        }
                    ],
                    "total": 1,
                },
            )
        if "/offer/offer123" in url and method == "GET":
            return FakeResponse(
                200,
                {
                    "offerId": "offer123",
                    "pricingSummary": {
                        "price": {"value": "10.00", "currency": "USD"}
                    },
                    "availableQuantity": 3,
                },
            )
        if "/offer/offer123" in url and method == "PUT":
            return FakeResponse(204, {})
        return FakeResponse(200, {})

    api._client.request.side_effect = mock_request

    result = await api.update_listing(
        "SKU001",
        {"price": "15.99", "quantity": 10},
    )
    assert result["sku"] == "SKU001"
    assert result["updated"] is True


@pytest.mark.asyncio
async def test_end_listing_success(api):
    async def mock_request(*args, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method", "")
        if "/offer" in url and method == "GET":
            return FakeResponse(
                200,
                {
                    "offers": [{"offerId": "offer123", "sku": "SKU001"}],
                    "total": 1,
                },
            )
        if "/withdraw" in url:
            return FakeResponse(200, {})
        return FakeResponse(200, {})

    api._client.request.side_effect = mock_request

    result = await api.end_listing("SKU001")
    assert result["sku"] == "SKU001"
    assert result["offer_id"] == "offer123"
    assert result["status"] == "ended"


@pytest.mark.asyncio
async def test_end_listing_no_offer_found(api):
    api._client.request.return_value = FakeResponse(
        200, {"offers": [], "total": 0}
    )
    with pytest.raises(EbayAPIError, match="No active offer found"):
        await api.end_listing("SKU001")


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_orders_success(api):
    api._client.request.return_value = FakeResponse(
        200,
        {
            "orders": [
                {"orderId": "order1", "buyer": {"username": "buyer1"}},
                {"orderId": "order2", "buyer": {"username": "buyer2"}},
            ],
            "total": 2,
        },
    )
    result = await api.get_orders(limit=10)
    assert len(result) == 2
    assert result[0]["orderId"] == "order1"
    _, kwargs = api._client.request.call_args
    assert kwargs["params"]["limit"] == 10


@pytest.mark.asyncio
async def test_get_orders_with_order_ids(api):
    api._client.request.return_value = FakeResponse(
        200, {"orders": [], "total": 0}
    )
    await api.get_orders(order_ids=["order1", "order2"])
    _, kwargs = api._client.request.call_args
    assert kwargs["params"]["orderIds"] == "order1,order2"


@pytest.mark.asyncio
async def test_get_orders_with_filter(api):
    api._client.request.return_value = FakeResponse(
        200, {"orders": [], "total": 0}
    )
    await api.get_orders(filter="orderfulfillmentstatus:{NOT_STARTED}")
    _, kwargs = api._client.request.call_args
    assert kwargs["params"]["filter"] == "orderfulfillmentstatus:{NOT_STARTED}"


@pytest.mark.asyncio
async def test_get_orders_limits_pagination(api):
    api._client.request.return_value = FakeResponse(
        200, {"orders": [], "total": 0}
    )
    await api.get_orders(limit=500, offset=-10)
    _, kwargs = api._client.request.call_args
    assert kwargs["params"]["limit"] == 200
    assert kwargs["params"]["offset"] == 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close(api):
    api._client.aclose = AsyncMock()
    await api.close()
    api._client.aclose.assert_awaited_once()
