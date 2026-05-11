import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.services import profit_service
from app.models.models import Order, OrderStatus


_NOW = datetime.now(timezone.utc)


def _make_mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


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


# ---------------------------------------------------------------------------
# calculate_order_profit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_order_profit_found():
    db = _make_mock_db()
    order = Order(
        id=1,
        ebay_order_id="order-1",
        sale_price=Decimal("100.00"),
        shipping_cost=Decimal("5.00"),
        ebay_fee=Decimal("10.00"),
        purchase_cost=Decimal("60.00"),
        profit=Decimal("35.00"),
        margin_percent=Decimal("33.33"),
        status=OrderStatus.pending,
    )
    db.execute.return_value = FakeResult([order])
    result = await profit_service.calculate_order_profit(db, 1)
    assert result is not None
    assert result.order_id == 1
    assert result.profit == Decimal("35.00")
    assert result.margin_percent == Decimal("33.33")


@pytest.mark.asyncio
async def test_calculate_order_profit_not_found():
    db = _make_mock_db()
    db.execute.return_value = FakeResult([])
    result = await profit_service.calculate_order_profit(db, 99)
    assert result is None


# ---------------------------------------------------------------------------
# get_profit_summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_profit_summary():
    db = _make_mock_db()

    class FakeAggResult:
        def scalar(self):
            return 5

        def one_or_none(self):
            return (
                Decimal("500.00"),
                Decimal("300.00"),
                Decimal("25.00"),
                Decimal("50.00"),
                Decimal("125.00"),
                Decimal("25.00"),
            )

    call_count = [0]

    def side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeAggResult()
        return FakeAggResult()

    db.execute.side_effect = side_effect

    result = await profit_service.get_profit_summary(db)
    assert result.total_orders == 5
    assert result.total_revenue == Decimal("500.00")
    assert result.total_purchase_cost == Decimal("300.00")
    assert result.total_shipping_cost == Decimal("25.00")
    assert result.total_ebay_fees == Decimal("50.00")
    assert result.total_profit == Decimal("125.00")
    assert result.average_margin_percent == Decimal("25.00")


# ---------------------------------------------------------------------------
# get_profit_details
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_profit_details():
    db = _make_mock_db()
    orders = [
        Order(
            id=1,
            ebay_order_id="o1",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("5.00"),
            ebay_fee=Decimal("10.00"),
            purchase_cost=Decimal("60.00"),
            profit=Decimal("35.00"),
            margin_percent=Decimal("33.33"),
            status=OrderStatus.pending,
            created_at=_NOW,
        ),
    ]
    db.execute.return_value = FakeResult(orders)
    result = await profit_service.get_profit_details(db)
    assert len(result) == 1
    assert result[0].order_id == 1
    assert result[0].profit == Decimal("35.00")


@pytest.mark.asyncio
async def test_get_profit_details_empty():
    db = _make_mock_db()
    db.execute.return_value = FakeResult([])
    result = await profit_service.get_profit_details(db)
    assert result == []


@pytest.mark.asyncio
async def test_get_profit_summary_rejects_invalid_date_range():
    db = _make_mock_db()
    with pytest.raises(ValueError, match="date_from must be before or equal to date_to"):
        await profit_service.get_profit_summary(
            db, date_from=_NOW, date_to=_NOW.replace(year=_NOW.year - 1)
        )


@pytest.mark.asyncio
async def test_get_profit_details_rejects_invalid_date_range():
    db = _make_mock_db()
    with pytest.raises(ValueError, match="date_from must be before or equal to date_to"):
        await profit_service.get_profit_details(
            db, date_from=_NOW, date_to=_NOW.replace(year=_NOW.year - 1)
        )
