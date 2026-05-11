import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.services.sourcing_service import search_and_source
from app.models.models import Product


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
    session.add = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_search_and_source_auto_create_listings():
    session = _make_mock_session()

    # No existing product by ASIN
    session.execute.return_value = FakeResult([])

    raw_items = [
        {
            "asin": "B08N5WRWNW",
            "title": "Test Product",
            "price": 19.99,
            "image_url": "https://img.jpg",
            "detail_page_url": "https://amazon.com/dp/B08N5WRWNW",
        }
    ]

    with patch(
        "app.services.sourcing_service.amazon_api.search_items",
        new_callable=AsyncMock,
        return_value=raw_items,
    ), patch(
        "app.services.sourcing_service._estimate_ebay_price",
        new_callable=AsyncMock,
        return_value=Decimal("50.00"),
    ), patch(
        "app.services.sourcing_service.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
    ) as mock_create_listing:
        results = await search_and_source(
            session, keywords=["test"], auto_create_listings=True
        )

    assert len(results) == 1
    assert results[0].asin == "B08N5WRWNW"
    mock_create_listing.assert_awaited_once()
    # The created product should be passed to listing creator.
    call_args = mock_create_listing.await_args
    assert call_args[0][0] == session


@pytest.mark.asyncio
async def test_search_and_source_no_auto_create():
    session = _make_mock_session()
    session.execute.return_value = FakeResult([])

    raw_items = [
        {
            "asin": "B08N5WRWNW",
            "title": "Test Product",
            "price": 19.99,
            "image_url": "https://img.jpg",
            "detail_page_url": "https://amazon.com/dp/B08N5WRWNW",
        }
    ]

    with patch(
        "app.services.sourcing_service.amazon_api.search_items",
        new_callable=AsyncMock,
        return_value=raw_items,
    ), patch(
        "app.services.sourcing_service._estimate_ebay_price",
        new_callable=AsyncMock,
        return_value=Decimal("50.00"),
    ), patch(
        "app.services.sourcing_service.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
    ) as mock_create_listing:
        results = await search_and_source(
            session, keywords=["test"], auto_create_listings=False
        )

    assert len(results) == 1
    mock_create_listing.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_and_source_auto_create_graceful_failure():
    session = _make_mock_session()
    session.execute.return_value = FakeResult([])

    raw_items = [
        {
            "asin": "B08N5WRWNW",
            "title": "Test Product",
            "price": 19.99,
            "image_url": "https://img.jpg",
            "detail_page_url": "https://amazon.com/dp/B08N5WRWNW",
        }
    ]

    with patch(
        "app.services.sourcing_service.amazon_api.search_items",
        new_callable=AsyncMock,
        return_value=raw_items,
    ), patch(
        "app.services.sourcing_service._estimate_ebay_price",
        new_callable=AsyncMock,
        return_value=Decimal("50.00"),
    ), patch(
        "app.services.sourcing_service.listing_creator.create_listing_from_product",
        new_callable=AsyncMock,
        side_effect=ValueError("Price calculation failed"),
    ) as mock_create_listing:
        results = await search_and_source(
            session, keywords=["test"], auto_create_listings=True
        )

    # Should still return sourcing results even if listing creation fails
    assert len(results) == 1
    mock_create_listing.assert_awaited_once()
