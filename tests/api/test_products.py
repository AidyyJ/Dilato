import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.models import Product, ProductSource

_NOW = datetime.now(timezone.utc)


pytestmark = pytest.mark.usefixtures("override_auth")


# ---------------------------------------------------------------------------
# GET /api/v1/products/{product_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_product_not_found(client):
    with patch(
        "app.api.v1.endpoints.products.product_service.get_product",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get("/api/v1/products/99")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/v1/products/asin/{asin}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_product_by_asin_not_found(client):
    with patch(
        "app.api.v1.endpoints.products.product_service.get_product_by_asin",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get("/api/v1/products/asin/B000000000")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
