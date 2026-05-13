import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PricingRule, Product, RuleType

logger = logging.getLogger(__name__)


async def get_active_rules(db: AsyncSession) -> List[PricingRule]:
    """Query all active pricing rules sorted by priority (highest first)."""
    result = await db.execute(
        select(PricingRule)
        .where(PricingRule.is_active == True)
        .order_by(PricingRule.priority.desc())
    )
    return list(result.scalars().all())


def apply_best_rule(
    amazon_price: Decimal,
    category: Optional[str],
    rules: List[PricingRule],
) -> Optional[Decimal]:
    """Pure function: iterate rules by priority, match on price range, return computed price."""
    for rule in rules:
        if not rule.is_active:
            continue

        # Price range matching
        if rule.min_price is not None and amazon_price < rule.min_price:
            continue
        if rule.max_price is not None and amazon_price > rule.max_price:
            continue

        # Category matching (exact string match if rule has a category filter)
        # Note: PricingRule model does not have a category field per spec,
        # so we skip category matching for now.

        computed = _compute_price(amazon_price, rule)
        if computed is None:
            continue

        # Margin check
        if rule.min_margin_percent is not None:
            margin = _calculate_margin(amazon_price, computed)
            if margin is None or margin < float(rule.min_margin_percent):
                continue

        return computed

    return None


def _compute_price(amazon_price: Decimal, rule: PricingRule) -> Optional[Decimal]:
    if rule.rule_type == RuleType.fixed_markup:
        return (amazon_price + rule.value).quantize(Decimal("0.01"))
    elif rule.rule_type == RuleType.percentage:
        return (amazon_price * (Decimal("1") + (rule.value / Decimal("100")))).quantize(Decimal("0.01"))
    elif rule.rule_type == RuleType.fixed_price:
        return Decimal(rule.value).quantize(Decimal("0.01"))
    return None


def _calculate_margin(amazon_price: Decimal, listing_price: Decimal) -> Optional[float]:
    """Calculate margin as a percentage."""
    if listing_price is None or listing_price <= 0:
        return None
    fee = listing_price * Decimal("0.13")
    margin = (listing_price - amazon_price - fee) / listing_price
    return float(margin)


async def calculate_listing_price(
    db: AsyncSession,
    product: Product,
    rules: Optional[List[PricingRule]] = None,
    rule_id: Optional[int] = None,
) -> Optional[Decimal]:
    """Given a Product and active rules, apply the highest-priority matching rule.

    If *rule_id* is provided, fetch that specific rule and apply it directly
    (still respecting price-range and margin constraints).
    """
    if product.amazon_price is None:
        return None

    if rule_id is not None:
        specific_rule = await get_rule(db, rule_id)
        if specific_rule is None:
            return None
        return apply_best_rule(product.amazon_price, product.category, [specific_rule])

    if rules is None:
        rules = await get_active_rules(db)

    return apply_best_rule(product.amazon_price, product.category, rules)


async def get_rule(db: AsyncSession, rule_id: int) -> Optional[PricingRule]:
    result = await db.execute(select(PricingRule).where(PricingRule.id == rule_id))
    return result.scalar_one_or_none()


async def create_rule(db: AsyncSession, rule_in) -> PricingRule:
    from app.schemas.schemas import PricingRuleCreate

    rule = PricingRule(
        name=rule_in.name,
        rule_type=rule_in.rule_type,
        value=rule_in.value,
        min_price=rule_in.min_price,
        max_price=rule_in.max_price,
        min_margin_percent=rule_in.min_margin_percent,
        priority=rule_in.priority,
        is_active=rule_in.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(db: AsyncSession, rule: PricingRule, rule_in) -> PricingRule:
    update_data = rule_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    # Cross-field validation for partial updates: ensure min_price <= max_price
    # considering both updated and existing values.
    if rule.min_price is not None and rule.max_price is not None and rule.min_price > rule.max_price:
        raise ValueError("min_price must be less than or equal to max_price")

    rule.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule: PricingRule) -> PricingRule:
    """Soft delete: deactivate the rule."""
    rule.is_active = False
    rule.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rule)
    return rule
