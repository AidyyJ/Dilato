import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.ebay_tasks import (
    _sync_ebay_listings,
    _publish_ebay_listing,
    sync_ebay_listings,
    publish_ebay_listing,
)
from app.models.models import (
    Listing,
    ListingStatus,
    Product,
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

    with patch("app.tasks.ebay_tasks.task_session", _ctx):
        yield session


@pytest.fixture
def mock_api():
    api = AsyncMock()
    api.close = AsyncMock()
    with patch("app.tasks.ebay_tasks.EbayAPI", return_value=api):
        yield api


# ---------------------------------------------------------------------------
# _sync_ebay_listings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_ebay_listings_active_to_ended(mock_task_session, mock_api):
    listing = Listing(
        id=1, status=ListingStatus.active, ebay_sku="SKU001", title="Test"
    )
    mock_task_session.execute.return_value = FakeResult([listing])
    mock_api._find_offer_by_sku.return_value = None

    result = await _sync_ebay_listings()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert listing.status == ListingStatus.ended
    assert listing.ended_at is not None


@pytest.mark.asyncio
async def test_sync_ebay_listings_ended_to_active(mock_task_session, mock_api):
    listing = Listing(
        id=1, status=ListingStatus.ended, ebay_sku="SKU001", title="Test"
    )
    mock_task_session.execute.return_value = FakeResult([listing])
    mock_api._find_offer_by_sku.return_value = {"offerId": "o1"}

    result = await _sync_ebay_listings()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert listing.status == ListingStatus.active
    assert listing.started_at is not None


@pytest.mark.asyncio
async def test_sync_ebay_listings_no_offer_with_fallback_sku(mock_task_session, mock_api):
    listing = Listing(id=2, status=ListingStatus.active, ebay_sku=None, title="Test")
    mock_task_session.execute.return_value = FakeResult([listing])
    mock_api._find_offer_by_sku.return_value = None

    result = await _sync_ebay_listings()
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    # SKU should fall back to LISTING-{id}
    mock_api._find_offer_by_sku.assert_awaited_with("LISTING-2")


# ---------------------------------------------------------------------------
# _publish_ebay_listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_ebay_listing_success(mock_task_session, mock_api):
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=5,
        ebay_category_id="1234",
        listing_duration="GTC",
    )
    product = Product(
        id=1, title="Test Product", brand="BrandX", image_url="https://img.jpg"
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    mock_task_session.execute.side_effect = side_effect
    mock_api.create_listing.return_value = {
        "item_id": "123456789",
        "offer_id": "offer123",
    }

    with patch(
        "app.tasks.ebay_tasks.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("35.00"),
    ) as mock_calc:
        result = await _publish_ebay_listing(1)
        mock_calc.assert_awaited_once()

    assert result["listing_id"] == 1
    assert result["ebay_item_id"] == "123456789"
    assert result["status"] == "active"
    assert listing.status == ListingStatus.active
    assert listing.ebay_sku == "LISTING-1"
    assert listing.started_at is not None
    # Price should be updated by pricing_service
    assert listing.listing_price == Decimal("35.00")


@pytest.mark.asyncio
async def test_publish_ebay_listing_not_found(mock_task_session, mock_api):
    mock_task_session.execute.return_value = FakeResult([])
    with pytest.raises(ValueError, match="Listing 99 not found"):
        await _publish_ebay_listing(99)


@pytest.mark.asyncio
async def test_publish_ebay_listing_product_not_found(mock_task_session, mock_api):
    listing = Listing(id=1, product_id=99, title="Test", listing_price=Decimal("10.00"))
    mock_task_session.execute.side_effect = [FakeResult([listing]), FakeResult([]), FakeResult([])]
    with pytest.raises(ValueError, match="Product for listing 1 not found"):
        await _publish_ebay_listing(1)


@pytest.mark.asyncio
async def test_publish_ebay_listing_null_price_fallback(mock_task_session, mock_api):
    """When calculated price is None and listing_price is 0, fall back to product.current_price."""
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("0"),
        quantity=5,
    )
    product = Product(
        id=1,
        title="Test Product",
        brand="BrandX",
        image_url="https://img.jpg",
        current_price=Decimal("19.99"),
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    mock_task_session.execute.side_effect = side_effect
    mock_api.create_listing.return_value = {"item_id": "123456789"}

    with patch(
        "app.tasks.ebay_tasks.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_calc:
        result = await _publish_ebay_listing(1)
        mock_calc.assert_awaited_once()

    assert result["listing_id"] == 1
    assert result["status"] == "active"
    # Should have fallen back to product.current_price
    assert listing.listing_price == Decimal("19.99")


@pytest.mark.asyncio
async def test_publish_ebay_listing_amazon_price_fallback(mock_task_session, mock_api):
    """When calculated price is None, listing_price is 0, and current_price is None,
    fall back to product.amazon_price."""
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("0"),
        quantity=5,
    )
    product = Product(
        id=1,
        title="Test Product",
        brand="BrandX",
        image_url="https://img.jpg",
        current_price=None,
        amazon_price=Decimal("15.99"),
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    mock_task_session.execute.side_effect = side_effect
    mock_api.create_listing.return_value = {"item_id": "123456789"}

    with patch(
        "app.tasks.ebay_tasks.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_calc:
        result = await _publish_ebay_listing(1)
        mock_calc.assert_awaited_once()

    assert result["listing_id"] == 1
    assert result["status"] == "active"
    assert listing.listing_price == Decimal("15.99")


@pytest.mark.asyncio
async def test_publish_ebay_listing_zero_calculated_price_fallback(mock_task_session, mock_api):
    """When calculate_listing_price returns Decimal('0'), fallback to product price."""
    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("29.99"),
        quantity=5,
    )
    product = Product(
        id=1,
        title="Test Product",
        brand="BrandX",
        image_url="https://img.jpg",
        current_price=Decimal("19.99"),
        amazon_price=None,
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    mock_task_session.execute.side_effect = side_effect
    mock_api.create_listing.return_value = {"item_id": "123456789"}

    with patch(
        "app.tasks.ebay_tasks.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("0"),
    ) as mock_calc:
        result = await _publish_ebay_listing(1)
        mock_calc.assert_awaited_once()

    assert result["listing_id"] == 1
    assert result["status"] == "active"
    # Should have fallen back to product.current_price because calculated was 0
    assert listing.listing_price == Decimal("19.99")


@pytest.mark.asyncio
async def test_publish_ebay_listing_fallback_logs_warning(
    mock_task_session, mock_api, caplog
):
    """When price fallback is used, a warning should be logged."""
    import logging

    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("0"),
        quantity=5,
    )
    product = Product(
        id=1,
        title="Test Product",
        brand="BrandX",
        image_url="https://img.jpg",
        current_price=Decimal("19.99"),
        amazon_price=None,
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    mock_task_session.execute.side_effect = side_effect
    mock_api.create_listing.return_value = {"item_id": "123456789"}

    with patch(
        "app.tasks.ebay_tasks.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with caplog.at_level(logging.WARNING, logger="app.tasks.ebay_tasks"):
            result = await _publish_ebay_listing(1)

    assert result["listing_id"] == 1
    assert "Price fallback used for listing 1" in caplog.text
    assert "falling back to product price (19.99)" in caplog.text


@pytest.mark.asyncio
async def test_publish_ebay_listing_null_price_raises(mock_task_session, mock_api, caplog):
    """When no valid price is available at all, raise ValueError and log error."""
    import logging

    listing = Listing(
        id=1,
        product_id=1,
        title="Test Listing",
        listing_price=Decimal("0"),
        quantity=5,
    )
    product = Product(
        id=1,
        title="Test Product",
        brand="BrandX",
        image_url="https://img.jpg",
        current_price=None,
        amazon_price=None,
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    mock_task_session.execute.side_effect = side_effect

    with patch(
        "app.tasks.ebay_tasks.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_calc:
        with caplog.at_level(logging.ERROR, logger="app.tasks.ebay_tasks"):
            with pytest.raises(ValueError, match="no valid price available"):
                await _publish_ebay_listing(1)
        mock_calc.assert_awaited_once()

    assert "Cannot publish listing 1: no valid price available" in caplog.text


# ---------------------------------------------------------------------------
# Sync wrappers
# ---------------------------------------------------------------------------

def test_sync_ebay_listings_wrapper():
    with patch(
        "app.tasks.ebay_tasks._sync_ebay_listings",
        new_callable=AsyncMock,
        return_value={"processed": 3},
    ) as mock_sync:
        result = sync_ebay_listings()
        assert result == {"processed": 3}
        mock_sync.assert_awaited_once()


def test_publish_ebay_listing_wrapper():
    with patch(
        "app.tasks.ebay_tasks._publish_ebay_listing",
        new_callable=AsyncMock,
        return_value={"status": "active"},
    ) as mock_sync:
        result = publish_ebay_listing(1)
        assert result == {"status": "active"}
        mock_sync.assert_awaited_once_with(1)


def test_sync_ebay_listings_wrapper_retry():
    with patch.object(
        sync_ebay_listings, "retry", side_effect=Exception("retry called")
    ) as mock_retry:
        with patch(
            "app.tasks.ebay_tasks.run_async",
            side_effect=Exception("fail"),
        ):
            with pytest.raises(Exception, match="retry called"):
                sync_ebay_listings()
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            countdown = kwargs.get("countdown")
            assert countdown is not None
            assert countdown != 60
            assert 0 < countdown <= 60


def test_publish_ebay_listing_wrapper_retry():
    with patch.object(
        publish_ebay_listing, "retry", side_effect=Exception("retry called")
    ) as mock_retry:
        with patch(
            "app.tasks.ebay_tasks.run_async",
            side_effect=Exception("fail"),
        ):
            with pytest.raises(Exception, match="retry called"):
                publish_ebay_listing(1)
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            countdown = kwargs.get("countdown")
            assert countdown is not None
            assert countdown != 60
            assert 0 < countdown <= 60
