import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.stock_sync import _sync_amazon_stock, sync_amazon_stock
from app.tasks.price_sync import _sync_amazon_prices, sync_amazon_prices
from app.models.models import (
    Product,
    Listing,
    ListingStatus,
    PriceHistory,
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

    with patch("app.tasks.stock_sync.task_session", _ctx), patch(
        "app.tasks.price_sync.task_session", _ctx
    ):
        yield session


@pytest.fixture
def mock_amazon_api():
    api = AsyncMock()
    api.close = AsyncMock()
    with patch("app.tasks.stock_sync.AmazonProductAPI", return_value=api):
        yield api


@pytest.fixture
def mock_ebay_api():
    api = AsyncMock()
    api.close = AsyncMock()
    with patch("app.tasks.stock_sync.EbayAPI", return_value=api), patch(
        "app.tasks.price_sync.EbayAPI", return_value=api
    ):
        yield api


# ---------------------------------------------------------------------------
# _sync_amazon_stock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_stock_success(mock_task_session, mock_amazon_api, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=1,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        # First call: select(Product)
        if "products" in str(query).lower():
            return FakeResult([product])
        # Second call: select(Listing) active
        return FakeResult([listing])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.return_value = [
        {"asin": "B08N5WRWNW", "price": Decimal("19.99"), "currency": "USD"}
    ]

    result = await _sync_amazon_stock()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert product.is_active is True
    assert listing.quantity == 5
    mock_ebay_api.update_listing.assert_awaited_once_with(
        "SKU001", {"quantity": 5}
    )


@pytest.mark.asyncio
async def test_sync_amazon_stock_unavailable(mock_task_session, mock_amazon_api, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=1,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult([product])
        return FakeResult([listing])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.return_value = []

    result = await _sync_amazon_stock()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert product.is_active is False
    assert listing.status == ListingStatus.ended
    mock_ebay_api.end_listing.assert_awaited_once_with("SKU001")


@pytest.mark.asyncio
async def test_sync_amazon_stock_no_products(mock_task_session, mock_amazon_api, mock_ebay_api):
    mock_task_session.execute.return_value = FakeResult([])
    result = await _sync_amazon_stock()
    assert result == {"processed": 0, "succeeded": 0, "failed": 0}


# ---------------------------------------------------------------------------
# _sync_amazon_prices
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_success(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("35.00"),
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 1
        assert listing.listing_price == Decimal("35.00")
        mock_ebay_api.update_listing.assert_awaited_once_with(
            "SKU001", {"price": "35.00", "currency": "USD"}
        )
        # PriceHistory should have been added with the new price
        added = [call.args[0] for call in mock_task_session.add.call_args_list]
        history = next((a for a in added if isinstance(a, PriceHistory)), None)
        assert history is not None
        assert history.price == Decimal("35.00")


@pytest.mark.asyncio
async def test_sync_amazon_prices_below_threshold(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("30.00"),
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("30.15"),
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 1
        # Price change is 0.5% — below 1% threshold
        assert listing.listing_price == Decimal("30.00")
        mock_ebay_api.update_listing.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_amazon_prices_no_listings(mock_task_session, mock_ebay_api):
    mock_task_session.execute.return_value = FakeResult([])
    result = await _sync_amazon_prices()
    assert result == {"processed": 0, "succeeded": 0, "failed": 0}


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_ebay_failure(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_ebay_api.update_listing.side_effect = Exception("eBay API error")

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("35.00"),
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 0
        assert result["failed"] == 1
        # DB should NOT be updated when eBay call fails
        assert listing.listing_price == Decimal("29.99")
        mock_ebay_api.update_listing.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_amazon_stock_ebay_update_failure(mock_task_session, mock_amazon_api, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=1,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult([product])
        return FakeResult([listing])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.return_value = [
        {"asin": "B08N5WRWNW", "price": Decimal("19.99"), "currency": "USD"}
    ]
    mock_ebay_api.update_listing.side_effect = Exception("eBay API error")

    result = await _sync_amazon_stock()
    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1
    # DB should NOT be updated when eBay call fails
    assert listing.quantity == 1
    mock_ebay_api.update_listing.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_amazon_stock_ebay_end_failure(mock_task_session, mock_amazon_api, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=1,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult([product])
        return FakeResult([listing])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.return_value = []
    mock_ebay_api.end_listing.side_effect = Exception("eBay API error")

    result = await _sync_amazon_stock()
    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1
    # Product is marked inactive because Amazon returned no item
    assert product.is_active is False
    # DB should NOT be updated when eBay call fails
    assert listing.status == ListingStatus.active
    mock_ebay_api.end_listing.assert_awaited_once()


# ---------------------------------------------------------------------------
# Sync wrappers
# ---------------------------------------------------------------------------

def test_sync_amazon_stock_wrapper():
    with patch(
        "app.tasks.stock_sync._sync_amazon_stock",
        new_callable=AsyncMock,
        return_value={"processed": 10},
    ) as mock_sync:
        result = sync_amazon_stock()
        assert result == {"processed": 10}
        mock_sync.assert_awaited_once()


def test_sync_amazon_prices_wrapper():
    with patch(
        "app.tasks.price_sync._sync_amazon_prices",
        new_callable=AsyncMock,
        return_value={"processed": 10},
    ) as mock_sync:
        result = sync_amazon_prices()
        assert result == {"processed": 10}
        mock_sync.assert_awaited_once()


# ---------------------------------------------------------------------------
# Amazon API chunk failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_stock_chunk_fetch_failure(mock_task_session, mock_amazon_api, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.side_effect = Exception("Amazon chunk error")

    result = await _sync_amazon_stock()
    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1
    mock_ebay_api.update_listing.assert_not_awaited()


# ---------------------------------------------------------------------------
# Product-level exception in stock sync
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_stock_product_exception(mock_task_session, mock_amazon_api, mock_ebay_api):
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=1,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult([product])
        return FakeResult([listing])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.return_value = [
        {"asin": "B08N5WRWNW", "price": Decimal("19.99"), "currency": "USD"}
    ]
    # Make ebay_sku truthiness evaluation raise to hit the outer product except
    listing.ebay_sku = MagicMock()
    listing.ebay_sku.__bool__ = MagicMock(side_effect=RuntimeError("sku bool error"))

    result = await _sync_amazon_stock()
    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1


# ---------------------------------------------------------------------------
# Multiple chunks trigger asyncio.sleep
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_stock_multiple_chunks(mock_task_session, mock_amazon_api, mock_ebay_api):
    products = [
        Product(
            id=i,
            asin=f"B08N5WRWNW{i:02d}",
            title=f"Test {i}",
            is_active=True,
        )
        for i in range(1, 12)
    ]

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult(products)
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect
    mock_amazon_api.get_items.return_value = []

    with patch(
        "app.tasks.stock_sync.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        result = await _sync_amazon_stock()
        assert result["processed"] == 11
        mock_sleep.assert_awaited_once_with(1)


# ---------------------------------------------------------------------------
# Outer exception in stock sync
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_stock_outer_exception(mock_task_session, mock_amazon_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        is_active=True,
    )

    def execute_side_effect(query):
        if "products" in str(query).lower():
            return FakeResult([product])
        raise Exception("db fail")

    mock_task_session.execute.side_effect = execute_side_effect

    with pytest.raises(Exception, match="db fail"):
        await _sync_amazon_stock()
    # create_sync_log commits once, complete_sync_log commits once
    assert mock_task_session.commit.call_count >= 2


# ---------------------------------------------------------------------------
# Celery wrapper retry — stock sync
# ---------------------------------------------------------------------------

def test_sync_amazon_stock_wrapper_retry():
    with patch.object(
        sync_amazon_stock, "retry", side_effect=Exception("retry called")
    ) as mock_retry:
        with patch(
            "app.tasks.stock_sync.run_async",
            side_effect=Exception("fail"),
        ):
            with pytest.raises(Exception, match="retry called"):
                sync_amazon_stock()
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            countdown = kwargs.get("countdown")
            assert countdown is not None
            assert countdown != 60
            assert 0 < countdown <= 60


# ---------------------------------------------------------------------------
# Price sync — new_price is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_new_price_none(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 1
        assert result["failed"] == 0
        mock_ebay_api.update_listing.assert_not_awaited()


# ---------------------------------------------------------------------------
# Price sync — old_price is zero (forces update)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_old_price_zero(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("0"),
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("35.00"),
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 1
        mock_ebay_api.update_listing.assert_awaited_once_with(
            "SKU001", {"price": "35.00", "currency": "USD"}
        )


# ---------------------------------------------------------------------------
# Price sync — old_price is None (forces update)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_old_price_none(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=None,
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("35.00"),
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 1
        assert listing.listing_price == Decimal("35.00")
        mock_ebay_api.update_listing.assert_awaited_once_with(
            "SKU001", {"price": "35.00", "currency": "USD"}
        )


# ---------------------------------------------------------------------------
# Product-level exception in price sync
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_product_exception(mock_task_session, mock_ebay_api):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=5,
        status=ListingStatus.active,
        ebay_sku="SKU001",
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            return FakeResult([listing])
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with patch(
        "app.tasks.price_sync.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.tasks.price_sync.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        side_effect=Exception("calc error"),
    ):
        result = await _sync_amazon_prices()
        assert result["processed"] == 1
        assert result["succeeded"] == 0
        assert result["failed"] == 1
        mock_ebay_api.update_listing.assert_not_awaited()


# ---------------------------------------------------------------------------
# Outer exception in price sync
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_amazon_prices_outer_exception(mock_task_session):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test",
        amazon_price=Decimal("20.00"),
        is_active=True,
    )

    def execute_side_effect(query):
        qs = str(query).lower()
        if "from listings" in qs:
            raise Exception("db fail")
        if "from products" in qs:
            return FakeResult([product])
        return FakeResult([])

    mock_task_session.execute.side_effect = execute_side_effect

    with pytest.raises(Exception, match="db fail"):
        await _sync_amazon_prices()
    assert mock_task_session.commit.call_count >= 2


# ---------------------------------------------------------------------------
# Celery wrapper retry — price sync
# ---------------------------------------------------------------------------

def test_sync_amazon_prices_wrapper_retry():
    with patch.object(
        sync_amazon_prices, "retry", side_effect=Exception("retry called")
    ) as mock_retry:
        with patch(
            "app.tasks.price_sync.run_async",
            side_effect=Exception("fail"),
        ):
            with pytest.raises(Exception, match="retry called"):
                sync_amazon_prices()
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            countdown = kwargs.get("countdown")
            assert countdown is not None
            assert countdown != 60
            assert 0 < countdown <= 60
