import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.models import Product, Listing, ListingStatus
from app.services.listing_creator import (
    generate_listing_title,
    generate_listing_description,
    create_listing_from_product,
    publish_listing,
    create_and_publish_listing,
)


# ---------------------------------------------------------------------------
# generate_listing_title
# ---------------------------------------------------------------------------

def test_generate_listing_title_short():
    product = Product(id=1, title="Short Title")
    assert generate_listing_title(product) == "Short Title"


def test_generate_listing_title_truncates_at_80():
    long_title = "A" * 100
    product = Product(id=1, title=long_title)
    result = generate_listing_title(product)
    assert len(result) <= 80
    # Should end at a word boundary (no trailing partial word)
    assert result.endswith("A")


def test_generate_listing_title_removes_restricted_words():
    product = Product(id=1, title="This is a counterfeit fake product")
    result = generate_listing_title(product)
    assert "counterfeit" not in result.lower()
    assert "fake" not in result.lower()
    assert "product" in result.lower()


def test_generate_listing_title_restricted_words_case_insensitive():
    product = Product(id=1, title="COUNTERFEIT ReplicA Fake")
    result = generate_listing_title(product)
    assert "counterfeit" not in result.lower()
    assert "replica" not in result.lower()
    assert "fake" not in result.lower()


def test_generate_listing_title_fallback_to_asin():
    product = Product(id=1, title="counterfeit replica", asin="B001234567")
    result = generate_listing_title(product)
    assert result == "B001234567"


def test_generate_listing_title_fallback_to_untitled():
    product = Product(id=1, title="counterfeit")
    result = generate_listing_title(product)
    assert result == "Untitled Listing"


# ---------------------------------------------------------------------------
# generate_listing_description
# ---------------------------------------------------------------------------

def test_generate_listing_description_basic():
    product = Product(
        id=1,
        title="Test Product",
        brand="BrandX",
        category="Electronics",
        detail_page_url="https://amazon.com/dp/B123",
    )
    desc = generate_listing_description(product, Decimal("29.99"))
    assert "Test Product" in desc
    assert "BrandX" in desc
    assert "Electronics" in desc
    assert "$29.99" in desc
    assert "https://amazon.com/dp/B123" in desc
    assert "Condition: New" in desc


def test_generate_listing_description_minimal():
    product = Product(id=1, title="Minimal")
    desc = generate_listing_description(product, Decimal("10.00"))
    assert "Minimal" in desc
    assert "$10.00" in desc


def test_generate_listing_description_rejects_javascript_url():
    product = Product(
        id=1,
        title="Bad Product",
        detail_page_url="javascript:alert('xss')",
    )
    desc = generate_listing_description(product, Decimal("10.00"))
    assert "javascript" not in desc
    assert "View on Amazon" not in desc


def test_generate_listing_description_rejects_data_url():
    product = Product(
        id=1,
        title="Bad Product",
        detail_page_url="data:text/html,<script>alert('xss')</script>",
    )
    desc = generate_listing_description(product, Decimal("10.00"))
    assert "data:" not in desc
    assert "View on Amazon" not in desc


def test_generate_listing_description_allows_https_url():
    product = Product(
        id=1,
        title="Good Product",
        detail_page_url="https://amazon.com/dp/B123",
    )
    desc = generate_listing_description(product, Decimal("10.00"))
    assert "https://amazon.com/dp/B123" in desc
    assert "View on Amazon" in desc


def test_generate_listing_description_escapes_html():
    product = Product(
        id=1,
        title='Widget <script>alert("xss")</script>',
        brand='Super&Bright"',
        category="Electronics > Gadgets",
    )
    desc = generate_listing_description(product, Decimal("19.99"))
    assert "<script>" not in desc
    assert 'alert("xss")' not in desc or "&quot;" in desc
    assert "&lt;script&gt;" in desc
    assert "&gt;" in desc
    assert "&amp;" in desc
    assert "&quot;" in desc
    assert ">" not in desc or "&gt;" in desc


# ---------------------------------------------------------------------------
# create_listing_from_product
# ---------------------------------------------------------------------------

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
    return session


@pytest.mark.asyncio
async def test_create_listing_from_product_success():
    session = _make_mock_session()
    product = Product(
        id=1,
        title="Great Product",
        brand="BrandY",
        amazon_price=Decimal("20.00"),
    )
    session.execute.return_value = FakeResult([product])

    with patch(
        "app.services.listing_creator.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("25.00"),
    ):
        listing = await create_listing_from_product(session, 1)

    assert listing.product_id == 1
    assert listing.status == ListingStatus.draft
    assert listing.listing_price == Decimal("25.00")
    assert listing.title == "Great Product"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_listing_from_product_with_rule_id():
    session = _make_mock_session()
    product = Product(id=1, title="Product", amazon_price=Decimal("10.00"))
    session.execute.return_value = FakeResult([product])

    with patch(
        "app.services.listing_creator.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("15.00"),
    ) as mock_calc:
        listing = await create_listing_from_product(session, 1, pricing_rule_id=42)

    mock_calc.assert_awaited_once_with(session, product, rule_id=42)
    assert listing.listing_price == Decimal("15.00")


@pytest.mark.asyncio
async def test_create_listing_from_product_not_found():
    session = _make_mock_session()
    session.execute.return_value = FakeResult([])

    with pytest.raises(ValueError, match="Product 99 not found"):
        await create_listing_from_product(session, 99)


@pytest.mark.asyncio
async def test_create_listing_from_product_price_calculation_fails():
    session = _make_mock_session()
    product = Product(id=1, title="Product", amazon_price=Decimal("10.00"))
    session.execute.return_value = FakeResult([product])

    with patch(
        "app.services.listing_creator.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(ValueError, match="Could not calculate listing price"):
            await create_listing_from_product(session, 1)


# ---------------------------------------------------------------------------
# publish_listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_listing_success():
    session = _make_mock_session()
    product = Product(id=1, title="Product", brand="BrandZ", image_url="https://img.jpg")
    listing = Listing(
        id=1,
        product_id=1,
        title="Product",
        listing_price=Decimal("30.00"),
        quantity=1,
        status=ListingStatus.draft,
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResult([listing])
        return FakeResult([product])

    session.execute.side_effect = side_effect

    mock_api = AsyncMock()
    mock_api.create_listing.return_value = {"item_id": "123456", "offer_id": "o1"}
    mock_api.close = AsyncMock()

    with patch(
        "app.services.listing_creator.EbayAPI", return_value=mock_api
    ), patch(
        "app.services.listing_creator.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("32.00"),
    ):
        result = await publish_listing(session, 1)

    assert result.status == ListingStatus.active
    assert result.ebay_item_id == "123456"
    assert result.ebay_sku == "LISTING-1"
    assert result.started_at is not None
    assert result.listing_price == Decimal("32.00")
    mock_api.create_listing.assert_awaited_once()
    mock_api.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_listing_not_found():
    session = _make_mock_session()
    session.execute.return_value = FakeResult([])

    with pytest.raises(ValueError, match="Listing 99 not found"):
        await publish_listing(session, 99)


@pytest.mark.asyncio
async def test_publish_listing_not_draft():
    session = _make_mock_session()
    listing = Listing(id=1, product_id=1, title="X", status=ListingStatus.active)
    session.execute.return_value = FakeResult([listing])

    with pytest.raises(ValueError, match="must be in draft status"):
        await publish_listing(session, 1)


# ---------------------------------------------------------------------------
# create_and_publish_listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_publish_listing():
    session = _make_mock_session()
    product = Product(id=1, title="Product", amazon_price=Decimal("20.00"))
    created_listing = Listing(
        id=1,
        product_id=1,
        title="Product",
        listing_price=Decimal("25.00"),
        quantity=1,
        status=ListingStatus.draft,
    )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        # 1st call: create_listing_from_product -> get_product
        # 2nd call: publish_listing -> get_listing
        # 3rd call: publish_listing -> get_product
        if call_count[0] == 1:
            return FakeResult([product])
        if call_count[0] == 2:
            return FakeResult([created_listing])
        return FakeResult([product])

    session.execute.side_effect = side_effect

    mock_api = AsyncMock()
    mock_api.create_listing.return_value = {"item_id": "789", "offer_id": "o2"}
    mock_api.close = AsyncMock()

    with patch(
        "app.services.listing_creator.EbayAPI", return_value=mock_api
    ), patch(
        "app.services.listing_creator.pricing_service.calculate_listing_price",
        new_callable=AsyncMock,
        return_value=Decimal("25.00"),
    ):
        result = await create_and_publish_listing(session, 1)

    assert result.status == ListingStatus.active
    assert result.ebay_item_id == "789"
    assert result.listing_price == Decimal("25.00")
    session.commit.assert_awaited()
