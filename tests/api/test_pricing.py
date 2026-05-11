import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.models import PricingRule, RuleType, Product
from app.schemas.schemas import PricingRuleCreate, PricingRuleUpdate


_NOW = datetime.now(timezone.utc)


pytestmark = pytest.mark.usefixtures("override_auth")


# ---------------------------------------------------------------------------
# list rules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_rules(client):
    rule = PricingRule(
        id=1,
        name="Test Rule",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=10,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[rule],
    ):
        response = await client.get("/api/v1/pricing/rules")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Rule"


# ---------------------------------------------------------------------------
# create rule
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_rule(client):
    rule = PricingRule(
        id=1,
        name="New Rule",
        rule_type=RuleType.percentage,
        value=Decimal("25.00"),
        priority=5,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.create_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ):
        response = await client.post(
            "/api/v1/pricing/rules",
            json={
                "name": "New Rule",
                "rule_type": "percentage",
                "value": "25.00",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Rule"
        assert data["rule_type"] == "percentage"


# ---------------------------------------------------------------------------
# update rule
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_rule(client):
    rule = PricingRule(
        id=1,
        name="Updated Rule",
        rule_type=RuleType.fixed_markup,
        value=Decimal("10.00"),
        priority=20,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ), patch(
        "app.api.v1.endpoints.pricing.pricing_service.update_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ):
        response = await client.patch(
            "/api/v1/pricing/rules/1",
            json={"name": "Updated Rule", "priority": 20},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule"


@pytest.mark.asyncio
async def test_update_rule_partial_max_price_violation(client):
    rule = PricingRule(
        id=1,
        name="Rule",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        min_price=Decimal("10.00"),
        max_price=Decimal("50.00"),
        priority=1,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ):
        response = await client.patch(
            "/api/v1/pricing/rules/1",
            json={"max_price": "5.00"},
        )
        assert response.status_code == 422
        assert "min_price must be less than or equal to max_price" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_rule_partial_min_price_violation(client):
    rule = PricingRule(
        id=1,
        name="Rule",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        min_price=Decimal("10.00"),
        max_price=Decimal("50.00"),
        priority=1,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ):
        response = await client.patch(
            "/api/v1/pricing/rules/1",
            json={"min_price": "100.00"},
        )
        assert response.status_code == 422
        assert "min_price must be less than or equal to max_price" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_rule_not_found(client):
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_rule",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.patch(
            "/api/v1/pricing/rules/99",
            json={"name": "Updated Rule"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# delete rule
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_rule(client):
    rule = PricingRule(
        id=1,
        name="Deleted Rule",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=1,
        is_active=False,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ), patch(
        "app.api.v1.endpoints.pricing.pricing_service.delete_rule",
        new_callable=AsyncMock,
        return_value=rule,
    ):
        response = await client.delete("/api/v1/pricing/rules/1")
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False


@pytest.mark.asyncio
async def test_delete_rule_not_found(client):
    with patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_rule",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.delete("/api/v1/pricing/rules/99")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# calculate price
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_price(client):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test Product",
        amazon_price=Decimal("20.00"),
        category="Electronics",
    )
    rule = PricingRule(
        id=1,
        name="Markup",
        rule_type=RuleType.fixed_markup,
        value=Decimal("5.00"),
        priority=10,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with patch(
        "app.api.v1.endpoints.pricing.product_service.get_product",
        new_callable=AsyncMock,
        return_value=product,
    ), patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[rule],
    ):
        response = await client.post(
            "/api/v1/pricing/calculate",
            json={"product_id": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["product_id"] == 1
        assert data["amazon_price"] == "20.00"
        assert data["listing_price"] == "25.00"
        assert data["rule_applied"]["name"] == "Markup"


@pytest.mark.asyncio
async def test_calculate_price_no_rules(client):
    product = Product(
        id=1,
        asin="B08N5WRWNW",
        title="Test Product",
        amazon_price=Decimal("20.00"),
        category="Electronics",
    )
    with patch(
        "app.api.v1.endpoints.pricing.product_service.get_product",
        new_callable=AsyncMock,
        return_value=product,
    ), patch(
        "app.api.v1.endpoints.pricing.pricing_service.get_active_rules",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = await client.post(
            "/api/v1/pricing/calculate",
            json={"product_id": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["listing_price"] is None
        assert data["rule_applied"] is None


@pytest.mark.asyncio
async def test_calculate_price_product_not_found(client):
    with patch(
        "app.api.v1.endpoints.pricing.product_service.get_product",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post(
            "/api/v1/pricing/calculate",
            json={"product_id": 99},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# schema validation
# ---------------------------------------------------------------------------


def test_create_rule_negative_value():
    with pytest.raises(ValueError, match="value must be non-negative"):
        PricingRuleCreate(
            name="Bad Rule",
            rule_type=RuleType.fixed_markup,
            value=Decimal("-5.00"),
            priority=1,
        )


def test_create_rule_min_price_greater_than_max_price():
    with pytest.raises(ValueError, match="min_price must be less than or equal to max_price"):
        PricingRuleCreate(
            name="Bad Rule",
            rule_type=RuleType.fixed_markup,
            value=Decimal("5.00"),
            min_price=Decimal("100.00"),
            max_price=Decimal("50.00"),
            priority=1,
        )


def test_update_rule_negative_value():
    with pytest.raises(ValueError, match="value must be non-negative"):
        PricingRuleUpdate(value=Decimal("-10.00"))


def test_update_rule_min_price_greater_than_max_price():
    with pytest.raises(ValueError, match="min_price must be less than or equal to max_price"):
        PricingRuleUpdate(min_price=Decimal("200.00"), max_price=Decimal("100.00"))


def test_create_rule_valid_min_max_price():
    rule = PricingRuleCreate(
        name="Good Rule",
        rule_type=RuleType.percentage,
        value=Decimal("25.00"),
        min_price=Decimal("10.00"),
        max_price=Decimal("100.00"),
        priority=1,
    )
    assert rule.min_price == Decimal("10.00")
    assert rule.max_price == Decimal("100.00")
