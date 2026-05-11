import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from app.models.models import PricingRule, RuleType, Product
from app.services.pricing_service import (
    apply_best_rule,
    calculate_listing_price,
    get_active_rules,
    create_rule,
    update_rule,
    delete_rule,
    _calculate_margin,
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
    session.add = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# apply_best_rule
# ---------------------------------------------------------------------------

def test_apply_best_rule_fixed_markup():
    rule = PricingRule(
        id=1,
        name="Fixed Markup",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [rule])
    assert result == Decimal("25.00")


def test_apply_best_rule_percentage():
    rule = PricingRule(
        id=1,
        name="30% Markup",
        rule_type=RuleType.percentage,
        value=Decimal("30.00"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [rule])
    assert result == Decimal("26.00")


def test_apply_best_rule_fixed_price():
    rule = PricingRule(
        id=1,
        name="Fixed Price",
        rule_type=RuleType.fixed_price,
        value=Decimal("99.99"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [rule])
    assert result == Decimal("99.99")


def test_apply_best_rule_no_match():
    rules = []
    result = apply_best_rule(Decimal("20.00"), None, rules)
    assert result is None


def test_apply_best_rule_priority_order():
    low_priority = PricingRule(
        id=1,
        name="Low",
        rule_type=RuleType.fixed_markup,
        value=Decimal("1.00"),
        priority=1,
        is_active=True,
    )
    high_priority = PricingRule(
        id=2,
        name="High",
        rule_type=RuleType.fixed_markup,
        value=Decimal("10.00"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [high_priority, low_priority])
    assert result == Decimal("30.00")


def test_apply_best_rule_inactive_skipped():
    active = PricingRule(
        id=1,
        name="Active",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=10,
        is_active=True,
    )
    inactive = PricingRule(
        id=2,
        name="Inactive",
        rule_type=RuleType.fixed_markup,
        value=Decimal("50.00"),
        priority=100,
        is_active=False,
    )
    result = apply_best_rule(Decimal("20.00"), None, [inactive, active])
    assert result == Decimal("25.00")


def test_apply_best_rule_min_price_filter():
    rule = PricingRule(
        id=1,
        name="Min Price",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        min_price=Decimal("50.00"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [rule])
    assert result is None


def test_apply_best_rule_max_price_filter():
    rule = PricingRule(
        id=1,
        name="Max Price",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        max_price=Decimal("10.00"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [rule])
    assert result is None


def test_apply_best_rule_margin_filter():
    rule = PricingRule(
        id=1,
        name="Margin Filter",
        rule_type=RuleType.fixed_markup,
        value=Decimal("1.00"),
        min_margin_percent=Decimal("50.00"),
        priority=10,
        is_active=True,
    )
    result = apply_best_rule(Decimal("20.00"), None, [rule])
    # margin = (21 - 20 - 2.73) / 21 = -1.73/21 ≈ -8.2% < 50%
    assert result is None


# ---------------------------------------------------------------------------
# _calculate_margin
# ---------------------------------------------------------------------------

def test_calculate_margin():
    margin = _calculate_margin(Decimal("20.00"), Decimal("30.00"))
    # fee = 30 * 0.13 = 3.90
    # margin = (30 - 20 - 3.90) / 30 = 6.10 / 30 ≈ 0.2033
    assert margin is not None
    assert 0.20 < margin < 0.21


def test_calculate_margin_zero_price():
    assert _calculate_margin(Decimal("20.00"), Decimal("0")) is None


# ---------------------------------------------------------------------------
# calculate_listing_price
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_listing_price_with_rules():
    product = Product(id=1, amazon_price=Decimal("20.00"), category="Electronics")
    rule = PricingRule(
        id=1,
        name="Markup",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=10,
        is_active=True,
    )
    result = await calculate_listing_price(None, product, rules=[rule])
    assert result == Decimal("25.00")


@pytest.mark.asyncio
async def test_calculate_listing_price_no_amazon_price():
    product = Product(id=1, amazon_price=None, category="Electronics")
    result = await calculate_listing_price(None, product, rules=[])
    assert result is None


# ---------------------------------------------------------------------------
# get_active_rules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_active_rules():
    session = _make_mock_session()
    rule1 = PricingRule(id=1, name="R1", rule_type=RuleType.fixed_markup, value=Decimal("1"), priority=1, is_active=True)
    rule2 = PricingRule(id=2, name="R2", rule_type=RuleType.fixed_markup, value=Decimal("2"), priority=2, is_active=True)
    session.execute.return_value = FakeResult([rule2, rule1])

    result = await get_active_rules(session)
    assert len(result) == 2
    assert result[0].priority == 2


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_rule():
    session = _make_mock_session()
    from app.schemas.schemas import PricingRuleCreate

    rule_in = PricingRuleCreate(
        name="Test Rule",
        rule_type=RuleType.percentage,
        value=Decimal("25.00"),
        priority=5,
    )
    rule = await create_rule(session, rule_in)
    assert rule.name == "Test Rule"
    assert rule.rule_type == RuleType.percentage
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule():
    session = _make_mock_session()
    from app.schemas.schemas import PricingRuleUpdate

    rule = PricingRule(
        id=1,
        name="Old",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=1,
        is_active=True,
    )
    update = PricingRuleUpdate(name="New", priority=10)
    updated = await update_rule(session, rule, update)
    assert updated.name == "New"
    assert updated.priority == 10
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_partial_max_price_violates_existing_min():
    session = _make_mock_session()
    from app.schemas.schemas import PricingRuleUpdate

    rule = PricingRule(
        id=1,
        name="Old",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        min_price=Decimal("10.00"),
        max_price=Decimal("50.00"),
        priority=1,
        is_active=True,
    )
    update = PricingRuleUpdate(max_price=Decimal("5.00"))
    with pytest.raises(ValueError, match="min_price must be less than or equal to max_price"):
        await update_rule(session, rule, update)


@pytest.mark.asyncio
async def test_update_rule_partial_min_price_violates_existing_max():
    session = _make_mock_session()
    from app.schemas.schemas import PricingRuleUpdate

    rule = PricingRule(
        id=1,
        name="Old",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        min_price=Decimal("10.00"),
        max_price=Decimal("50.00"),
        priority=1,
        is_active=True,
    )
    update = PricingRuleUpdate(min_price=Decimal("100.00"))
    with pytest.raises(ValueError, match="min_price must be less than or equal to max_price"):
        await update_rule(session, rule, update)


@pytest.mark.asyncio
async def test_delete_rule():
    session = _make_mock_session()
    rule = PricingRule(
        id=1,
        name="Rule",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=1,
        is_active=True,
    )
    deactivated = await delete_rule(session, rule)
    assert deactivated.is_active is False
    session.commit.assert_awaited_once()
