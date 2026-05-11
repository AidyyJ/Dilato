import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Order, OrderStatus
from app.schemas.schemas import OrderProfitDetailOut, ProfitSummaryOut
from app.services import order_service

logger = logging.getLogger(__name__)


async def calculate_order_profit(
    db: AsyncSession,
    order_id: int,
) -> Optional[OrderProfitDetailOut]:
    """Compute and return the profit breakdown for a single order."""
    order = await order_service.get_order(db, order_id)
    if not order:
        return None

    # Recalculate in case underlying values changed
    if order.purchase_cost is not None:
        order.profit, order.margin_percent = order_service.calculate_profit(
            order.sale_price,
            order.shipping_cost,
            order.ebay_fee,
            order.purchase_cost,
        )
        await db.commit()
        await db.refresh(order)

    return OrderProfitDetailOut(
        order_id=order.id,
        ebay_order_id=order.ebay_order_id,
        sale_price=order.sale_price,
        shipping_cost=order.shipping_cost,
        ebay_fee=order.ebay_fee,
        purchase_cost=order.purchase_cost,
        profit=order.profit,
        margin_percent=order.margin_percent,
    )


async def get_profit_summary(
    db: AsyncSession,
    status: Optional[OrderStatus] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> ProfitSummaryOut:
    """Return aggregated profit metrics across orders with optional filters."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from must be before or equal to date_to")

    # Build base filter
    filters = []
    if status is not None:
        filters.append(Order.status == status)
    if date_from is not None:
        filters.append(Order.created_at >= date_from)
    if date_to is not None:
        filters.append(Order.created_at <= date_to)

    # Count total orders matching filters
    count_query = select(func.count(Order.id))
    if filters:
        count_query = count_query.where(*filters)
    count_result = await db.execute(count_query)
    total_orders = count_result.scalar() or 0

    # Aggregate sums across orders that have profit calculated
    agg_query = select(
        func.coalesce(func.sum(Order.sale_price), Decimal("0")),
        func.coalesce(func.sum(Order.purchase_cost), Decimal("0")),
        func.coalesce(func.sum(Order.shipping_cost), Decimal("0")),
        func.coalesce(func.sum(Order.ebay_fee), Decimal("0")),
        func.coalesce(func.sum(Order.profit), Decimal("0")),
        func.coalesce(func.avg(Order.margin_percent), Decimal("0")),
    ).where(Order.profit.isnot(None))

    if filters:
        agg_query = agg_query.where(*filters)

    agg_result = await db.execute(agg_query)
    row = agg_result.one_or_none()
    if row:
        (
            total_revenue,
            total_purchase_cost,
            total_shipping_cost,
            total_ebay_fees,
            total_profit,
            average_margin_percent,
        ) = row
    else:
        total_revenue = Decimal("0")
        total_purchase_cost = Decimal("0")
        total_shipping_cost = Decimal("0")
        total_ebay_fees = Decimal("0")
        total_profit = Decimal("0")
        average_margin_percent = Decimal("0")

    return ProfitSummaryOut(
        total_orders=total_orders,
        total_revenue=Decimal(str(round(total_revenue, 2))),
        total_purchase_cost=Decimal(str(round(total_purchase_cost, 2))),
        total_shipping_cost=Decimal(str(round(total_shipping_cost, 2))),
        total_ebay_fees=Decimal(str(round(total_ebay_fees, 2))),
        total_profit=Decimal(str(round(total_profit, 2))),
        average_margin_percent=Decimal(str(round(average_margin_percent, 2))),
    )


async def get_profit_details(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: Optional[OrderStatus] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[OrderProfitDetailOut]:
    """Return a paginated list of order profit breakdowns."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from must be before or equal to date_to")

    query = select(Order).where(Order.profit.isnot(None))

    if status is not None:
        query = query.where(Order.status == status)
    if date_from is not None:
        query = query.where(Order.created_at >= date_from)
    if date_to is not None:
        query = query.where(Order.created_at <= date_to)

    query = query.offset(skip).limit(limit).order_by(Order.created_at.desc())
    result = await db.execute(query)
    orders = list(result.scalars().all())

    return [
        OrderProfitDetailOut(
            order_id=order.id,
            ebay_order_id=order.ebay_order_id,
            sale_price=order.sale_price,
            shipping_cost=order.shipping_cost,
            ebay_fee=order.ebay_fee,
            purchase_cost=order.purchase_cost,
            profit=order.profit,
            margin_percent=order.margin_percent,
        )
        for order in orders
    ]
