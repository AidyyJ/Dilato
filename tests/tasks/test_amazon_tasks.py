import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.amazon_tasks import (
    _sync_amazon_products,
    _refresh_amazon_prices,
    sync_amazon_products,
    refresh_amazon_prices,
)
from app.models.models import Product, PriceHistory, SyncStatus, SyncType


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

    with patch("app.tasks.amazon_tasks.task_session", _ctx):
        yield session


@pytest.fixture
def mock_api():
    api = AsyncMock()
    api.close = AsyncMock()
    with patch("app.tasks.amazon_tasks.AmazonProductAPI", return_value=api):
        yield api


# ---------------------------------------------------------------------------
# _sync_amazon_products
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_products_success(mock_task_session, mock_api):
    mock_api.search_items.return_value = [
        {
            "asin": "B08N5WRWNW",
            "title": "Test Product",
            "brand": "TestBrand",
            "category": "Electronics",
            "image_url": "https://example.com/img.jpg",
            "detail_page_url": "https://amazon.com/dp/B08N5WRWNW",
            "price": Decimal("19.99"),
        }
    ]
    with patch(
        "app.tasks.amazon_tasks.upsert_product_from_amazon", new_callable=AsyncMock
    ) as mock_upsert:
        result = await _sync_amazon_products(keywords="test")
        assert result == {"processed": 1, "succeeded": 1, "failed": 0}
        mock_upsert.assert_awaited_once()
        assert mock_task_session.commit.call_count >= 1


@pytest.mark.asyncio
async def test_sync_amazon_products_api_failure(mock_task_session, mock_api):
    from app.services.amazon_api import AmazonAPIError

    mock_api.search_items.side_effect = AmazonAPIError("API down")
    with pytest.raises(AmazonAPIError, match="API down"):
        await _sync_amazon_products(keywords="test")
    # SyncLog should be created and then updated to failed
    assert mock_task_session.commit.call_count >= 1


@pytest.mark.asyncio
async def test_sync_amazon_products_upsert_failure(mock_task_session, mock_api):
    mock_api.search_items.return_value = [
        {
            "asin": "B08N5WRWNW",
            "title": "Test Product",
            "price": Decimal("19.99"),
        }
    ]
    with patch(
        "app.tasks.amazon_tasks.upsert_product_from_amazon",
        new_callable=AsyncMock,
        side_effect=Exception("DB error"),
    ):
        result = await _sync_amazon_products(keywords="test")
        assert result["processed"] == 1
        assert result["succeeded"] == 0
        assert result["failed"] == 1


# ---------------------------------------------------------------------------
# _refresh_amazon_prices
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_amazon_prices_success(mock_task_session, mock_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        current_price=Decimal("19.99"),
        is_active=True,
    )
    mock_task_session.execute.return_value = FakeResult([product])
    mock_api.get_items.return_value = [
        {"asin": "B08N5WRWNW", "price": Decimal("21.99"), "currency": "USD"}
    ]
    result = await _refresh_amazon_prices()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    # PriceHistory should have been added with the new price
    added = [call.args[0] for call in mock_task_session.add.call_args_list]
    history = next((a for a in added if isinstance(a, PriceHistory)), None)
    assert history is not None
    assert history.price == Decimal("21.99")
    assert product.current_price == Decimal("21.99")
    assert product.amazon_price == Decimal("21.99")


@pytest.mark.asyncio
async def test_refresh_amazon_prices_no_change(mock_task_session, mock_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        current_price=Decimal("19.99"),
        is_active=True,
    )
    mock_task_session.execute.return_value = FakeResult([product])
    mock_api.get_items.return_value = [
        {"asin": "B08N5WRWNW", "price": Decimal("19.99"), "currency": "USD"}
    ]
    result = await _refresh_amazon_prices()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    # No PriceHistory when price unchanged
    added = [call.args[0] for call in mock_task_session.add.call_args_list]
    assert not any(isinstance(a, PriceHistory) for a in added)


@pytest.mark.asyncio
async def test_refresh_amazon_prices_no_products(mock_task_session, mock_api):
    mock_task_session.execute.return_value = FakeResult([])
    result = await _refresh_amazon_prices()
    assert result == {"processed": 0, "succeeded": 0, "failed": 0}


@pytest.mark.asyncio
async def test_refresh_amazon_prices_chunk_failure(mock_task_session, mock_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        current_price=Decimal("19.99"),
        is_active=True,
    )
    mock_task_session.execute.return_value = FakeResult([product])
    mock_api.get_items.side_effect = Exception("Network error")
    result = await _refresh_amazon_prices()
    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1


# ---------------------------------------------------------------------------
# Sync wrappers
# ---------------------------------------------------------------------------

def test_sync_amazon_products_wrapper():
    with patch(
        "app.tasks.amazon_tasks._sync_amazon_products",
        new_callable=AsyncMock,
        return_value={"processed": 5},
    ) as mock_sync:
        result = sync_amazon_products(keywords="test")
        assert result == {"processed": 5}
        mock_sync.assert_awaited_once_with("test", None)


def test_refresh_amazon_prices_wrapper():
    with patch(
        "app.tasks.amazon_tasks._refresh_amazon_prices",
        new_callable=AsyncMock,
        return_value={"processed": 10},
    ) as mock_refresh:
        result = refresh_amazon_prices()
        assert result == {"processed": 10}
        mock_refresh.assert_awaited_once()
