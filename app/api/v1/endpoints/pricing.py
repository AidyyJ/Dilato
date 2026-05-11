from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    PricingRuleOut,
    PricingRuleCreate,
    PricingRuleUpdate,
    PricingCalculateRequest,
    PricingCalculateResponse,
)
from app.services import pricing_service, product_service

router = APIRouter()


@router.get("/rules", response_model=List[PricingRuleOut])
async def list_rules(db: AsyncSession = Depends(get_db)):
    rules = await pricing_service.get_active_rules(db)
    return rules


@router.post("/rules", response_model=PricingRuleOut, status_code=201)
async def create_rule(rule_in: PricingRuleCreate, db: AsyncSession = Depends(get_db)):
    rule = await pricing_service.create_rule(db, rule_in)
    return rule


@router.patch("/rules/{rule_id}", response_model=PricingRuleOut)
async def update_rule(rule_id: int, rule_in: PricingRuleUpdate, db: AsyncSession = Depends(get_db)):
    rule = await pricing_service.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    try:
        updated = await pricing_service.update_rule(db, rule, rule_in)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return updated


@router.delete("/rules/{rule_id}", response_model=PricingRuleOut)
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await pricing_service.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    deactivated = await pricing_service.delete_rule(db, rule)
    return deactivated


@router.post("/calculate", response_model=PricingCalculateResponse)
async def calculate_price(payload: PricingCalculateRequest, db: AsyncSession = Depends(get_db)):
    product = await product_service.get_product(db, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    rules = await pricing_service.get_active_rules(db)
    listing_price = pricing_service.apply_best_rule(
        product.amazon_price, product.category, rules
    )

    rule_applied = None
    if listing_price is not None:
        for rule in rules:
            computed = pricing_service.apply_best_rule(product.amazon_price, product.category, [rule])
            if computed == listing_price:
                rule_applied = rule
                break

    return PricingCalculateResponse(
        product_id=product.id,
        amazon_price=product.amazon_price,
        listing_price=listing_price,
        rule_applied=rule_applied,
    )
