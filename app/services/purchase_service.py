import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Order, FulfillmentStatus
from app.schemas.schemas import OrderPurchase
from app.services import order_service

logger = logging.getLogger(__name__)


def generate_amazon_purchase_link(order: Order) -> Optional[str]:
    """Construct an Amazon add-to-cart URL using the product's ASIN.

    Traverses Order -> Listing -> Product to find the ASIN.
    Returns None if no ASIN can be resolved.
    """
    listing = order.listing
    if not listing:
        logger.warning(
            "Cannot generate purchase link: order %s has no linked listing", order.id
        )
        return None

    product = listing.product
    if not product:
        logger.warning(
            "Cannot generate purchase link: listing %s has no linked product", listing.id
        )
        return None

    asin = product.asin
    if not asin:
        logger.warning("Cannot generate purchase link: product %s has no ASIN", product.id)
        return None

    quantity = order.quantity or 1
    return (
        f"https://www.amazon.com/gp/aws/cart/add.html"
        f"?ASIN.1={asin}&Quantity.1={quantity}"
    )


async def mark_order_purchased(
    db: AsyncSession,
    order_id: int,
    amazon_order_id: Optional[str] = None,
    purchase_cost: Optional[Decimal] = None,
    amazon_purchase_url: Optional[str] = None,
    fulfillment_status: Optional[FulfillmentStatus] = None,
) -> Optional[Order]:
    """Mark an order as purchased on Amazon and recalculate profit.

    If *amazon_purchase_url* is omitted, one is auto-generated from the
    linked product's ASIN.
    """
    order = await order_service.get_order_with_product(db, order_id)
    if not order:
        return None

    if amazon_purchase_url is None:
        amazon_purchase_url = generate_amazon_purchase_link(order)

    purchase_data = OrderPurchase(
        amazon_purchase_url=amazon_purchase_url,
        purchase_cost=purchase_cost,
        amazon_order_id=amazon_order_id,
        fulfillment_status=fulfillment_status,
    )

    return await order_service.record_purchase(db, order, purchase_data)
