from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import OrderStatus
from app.schemas.schemas import (
    OrderOut,
    OrderWebhookPayload,
    OrderStatusUpdate,
    OrderFulfillmentUpdate,
    OrderUpdate,
    OrderPurchase,
    OrderProfitDetailOut,
    ProfitSummaryOut,
    PurchaseLinkOut,
)
from app.services import order_service, purchase_service, profit_service

# Authenticated router for internal order management
router = APIRouter()

# Unauthenticated router for eBay webhooks
webhook_router = APIRouter()


@router.get("/", response_model=List[OrderOut])
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    status: Optional[OrderStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    orders = await order_service.list_orders(db, skip=skip, limit=limit, status=status)
    return orders


# ---------------------------------------------------------------------------
# Profit tracking — must be defined BEFORE /{order_id} routes
# ---------------------------------------------------------------------------

@router.get("/profit/summary", response_model=ProfitSummaryOut)
async def get_profit_summary(
    status: Optional[OrderStatus] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated profit metrics across orders with optional filters."""
    try:
        summary = await profit_service.get_profit_summary(
            db, status=status, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return summary


@router.get("/profit/details", response_model=List[OrderProfitDetailOut])
async def get_profit_details(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[OrderStatus] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of per-order profit breakdowns."""
    try:
        details = await profit_service.get_profit_details(
            db, skip=skip, limit=limit, status=status, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return details


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@webhook_router.post("/webhook", response_model=OrderOut, status_code=201)
async def order_webhook(payload: OrderWebhookPayload, db: AsyncSession = Depends(get_db)):
    """Receive an eBay order webhook and create or update the corresponding order.

    This endpoint is intentionally unauthenticated so that eBay can push
    order events directly.
    """
    try:
        order = await order_service.process_order_webhook(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return order


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: int,
    update: OrderUpdate,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await order_service.update_order(db, order, update)
    return updated


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    update: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await order_service.update_order_status(db, order, update)
    return updated


@router.patch("/{order_id}/fulfillment", response_model=OrderOut)
async def update_order_fulfillment(
    order_id: int,
    update: OrderFulfillmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await order_service.update_order_fulfillment(db, order, update)
    return updated


# ---------------------------------------------------------------------------
# Purchase automation
# ---------------------------------------------------------------------------

@router.post("/{order_id}/purchase-link", response_model=PurchaseLinkOut)
async def generate_purchase_link(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate an Amazon purchase URL for an order using the linked product's ASIN."""
    order = await order_service.get_order_with_product(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    link = purchase_service.generate_amazon_purchase_link(order)
    return PurchaseLinkOut(order_id=order.id, purchase_url=link)


@router.post("/{order_id}/mark-purchased", response_model=OrderOut)
async def mark_purchased(
    order_id: int,
    purchase: OrderPurchase,
    db: AsyncSession = Depends(get_db),
):
    """Mark an order as purchased on Amazon and recalculate profit / margin."""
    order = await purchase_service.mark_order_purchased(
        db,
        order_id=order_id,
        amazon_order_id=purchase.amazon_order_id,
        purchase_cost=purchase.purchase_cost,
        amazon_purchase_url=purchase.amazon_purchase_url,
        fulfillment_status=purchase.fulfillment_status,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------------
# Single-order profit
# ---------------------------------------------------------------------------

@router.get("/{order_id}/profit", response_model=OrderProfitDetailOut)
async def get_order_profit(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return the profit breakdown for a single order."""
    detail = await profit_service.calculate_order_profit(db, order_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Order not found")
    return detail
