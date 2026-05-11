import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.models import Listing, ListingStatus, Product
from app.services.ebay_api import EbayAPIError

_NOW = datetime.now(timezone.utc)


pytestmark = pytest.mark.usefixtures("override_auth")


# ---------------------------------------------------------------------------
# POST /api/v1/listings/create-from-product
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_from_product(client):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test Product",
        amazon_price=Decimal("20.00"),
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Product",
        listing_price=Decimal("25.00"),
        quantity=1,
        quantity_sold=0,
        status=ListingStatus.draft,
        listing_duration="GTC",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
        return_value=listing,
    ):
        response = await client.post(
            "/api/v1/listings/create-from-product",
            json={"product_id": 1},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["product_id"] == 1
        assert data["status"] == "draft"
        assert data["listing_price"] == "25.00"


@pytest.mark.asyncio
async def test_create_from_product_with_rule(client):
    listing = Listing(
        id=2,
        product_id=1,
        title="Test Product",
        listing_price=Decimal("30.00"),
        quantity=1,
        quantity_sold=0,
        status=ListingStatus.draft,
        listing_duration="GTC",
        created_at=_NOW,
        updated_at=_NOW,
    )
    mock_create = AsyncMock(return_value=listing)
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
        return_value=listing,
    ) as mock_create:
        response = await client.post(
            "/api/v1/listings/create-from-product",
            json={"product_id": 1, "pricing_rule_id": 5},
        )
        assert response.status_code == 201
        mock_create.assert_awaited_once()
        call_args = mock_create.await_args
        assert call_args[0][1] == 1
        assert call_args[0][2] == 5


@pytest.mark.asyncio
async def test_create_from_product_not_found(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
        side_effect=ValueError("Product 99 not found"),
    ):
        response = await client.post(
            "/api/v1/listings/create-from-product",
            json={"product_id": 99},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_from_product_wrong_status(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
        side_effect=ValueError("Product 1 is not eligible"),
    ):
        response = await client.post(
            "/api/v1/listings/create-from-product",
            json={"product_id": 1},
        )
        assert response.status_code == 422
        assert "not eligible" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_from_product_price_calculation_fails(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
        side_effect=ValueError("Could not calculate listing price for product 1"),
    ):
        response = await client.post(
            "/api/v1/listings/create-from-product",
            json={"product_id": 1},
        )
        assert response.status_code == 422
        assert "calculate" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/v1/listings/{listing_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_listing_not_found(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_service.get_listing",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get("/api/v1/listings/99")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/v1/listings/{id}/publish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_listing(client):
    listing = Listing(
        id=1,
        product_id=1,
        title="Test",
        listing_price=Decimal("25.00"),
        quantity=1,
        quantity_sold=0,
        status=ListingStatus.active,
        ebay_item_id="123456",
        ebay_sku="LISTING-1",
        listing_duration="GTC",
        started_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.publish_listing",
        new_callable=AsyncMock,
        return_value=listing,
    ):
        response = await client.post("/api/v1/listings/1/publish")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["ebay_item_id"] == "123456"


@pytest.mark.asyncio
async def test_publish_listing_not_found(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.publish_listing",
        new_callable=AsyncMock,
        side_effect=ValueError("Listing 99 not found"),
    ):
        response = await client.post("/api/v1/listings/99/publish")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_publish_listing_wrong_status(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.publish_listing",
        new_callable=AsyncMock,
        side_effect=ValueError("Listing 1 must be in draft status"),
    ):
        response = await client.post("/api/v1/listings/1/publish")
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_publish_listing_ebay_api_error(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.publish_listing",
        new_callable=AsyncMock,
        side_effect=EbayAPIError("eBay API returned 502"),
    ):
        response = await client.post("/api/v1/listings/1/publish")
        assert response.status_code == 502
        assert "502" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/v1/listings/create-and-publish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_publish(client):
    listing = Listing(
        id=1,
        product_id=1,
        title="Test",
        listing_price=Decimal("25.00"),
        quantity=1,
        quantity_sold=0,
        status=ListingStatus.active,
        ebay_item_id="123456",
        listing_duration="GTC",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_and_publish_listing",
        new_callable=AsyncMock,
        return_value=listing,
    ):
        response = await client.post(
            "/api/v1/listings/create-and-publish",
            json={"product_id": 1},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert data["ebay_item_id"] == "123456"


@pytest.mark.asyncio
async def test_create_and_publish_not_found(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_and_publish_listing",
        new_callable=AsyncMock,
        side_effect=ValueError("Product 99 not found"),
    ):
        response = await client.post(
            "/api/v1/listings/create-and-publish",
            json={"product_id": 99},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_and_publish_wrong_status(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_and_publish_listing",
        new_callable=AsyncMock,
        side_effect=ValueError("Product 1 is not eligible"),
    ):
        response = await client.post(
            "/api/v1/listings/create-and-publish",
            json={"product_id": 1},
        )
        assert response.status_code == 422
        assert "not eligible" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_and_publish_ebay_api_error(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_creator.create_and_publish_listing",
        new_callable=AsyncMock,
        side_effect=EbayAPIError("eBay API returned 502"),
    ):
        response = await client.post(
            "/api/v1/listings/create-and-publish",
            json={"product_id": 1},
        )
        assert response.status_code == 502
        assert "502" in response.json()["detail"]


# ---------------------------------------------------------------------------
# PATCH /api/v1/listings/{listing_id}/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_listing_status_not_found(client):
    with patch(
        "app.api.v1.endpoints.listings.listing_service.update_listing_status",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.patch("/api/v1/listings/99/status?status=active")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/v1/listings (updated with auto-calculate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_listing_auto_calculate_price(client):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test Product",
        amazon_price=Decimal("20.00"),
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Custom Title",
        listing_price=Decimal("25.00"),
        quantity=1,
        quantity_sold=0,
        status=ListingStatus.draft,
        listing_duration="GTC",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.listings.product_service.get_product",
        new_callable=AsyncMock,
        return_value=product,
    ), patch(
        "app.api.v1.endpoints.listings.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("25.00"),
    ), patch(
        "app.api.v1.endpoints.listings.listing_service.create_listing",
        new_callable=AsyncMock,
        return_value=listing,
    ) as mock_create:
        response = await client.post(
            "/api/v1/listings/",
            json={
                "product_id": 1,
                "title": "Custom Title",
                # listing_price omitted
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["listing_price"] == "25.00"
        # Verify the resolved ListingCreate passed to the service has the price
        call_args = mock_create.await_args
        passed = call_args[0][1]
        assert passed.listing_price == Decimal("25.00")


@pytest.mark.asyncio
async def test_create_listing_explicit_price(client):
    listing = Listing(
        id=1,
        product_id=1,
        title="Custom Title",
        listing_price=Decimal("99.99"),
        quantity=1,
        quantity_sold=0,
        status=ListingStatus.draft,
        listing_duration="GTC",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.listings.listing_service.create_listing",
        new_callable=AsyncMock,
        return_value=listing,
    ) as mock_create:
        response = await client.post(
            "/api/v1/listings/",
            json={
                "product_id": 1,
                "title": "Custom Title",
                "listing_price": "99.99",
            },
        )
        assert response.status_code == 201
        call_args = mock_create.await_args
        passed = call_args[0][1]
        assert passed.listing_price == Decimal("99.99")


@pytest.mark.asyncio
async def test_create_listing_product_not_found(client):
    with patch(
        "app.api.v1.endpoints.listings.product_service.get_product",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post(
            "/api/v1/listings/",
            json={"product_id": 99, "title": "Title"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_listing_price_calculation_fails(client):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test Product",
        amazon_price=Decimal("20.00"),
    )
    with patch(
        "app.api.v1.endpoints.listings.product_service.get_product",
        new_callable=AsyncMock,
        return_value=product,
    ), patch(
        "app.api.v1.endpoints.listings.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post(
            "/api/v1/listings/",
            json={"product_id": 1, "title": "Title"},
        )
        assert response.status_code == 422
        assert "Unable to calculate listing price" in response.json()["detail"]
