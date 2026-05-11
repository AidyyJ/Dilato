import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Order, OrderStatus, Listing, ListingStatus
from app.schemas.schemas import (
    OrderWebhookPayload,
    OrderStatusUpdate,
    OrderFulfillmentUpdate,
    OrderUpdate,
    OrderPurchase,
)

logger = logging.getLogger(__name__)


def calculate_profit(
    sale_price: Decimal,
    shipping_cost: Optional[Decimal] = None,
    ebay_fee: Optional[Decimal] = None,
    purchase_cost: Optional[Decimal] = None,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Compute profit and margin_percent from order economics.

    Returns (profit, margin_percent).  If *purchase_cost* is None,
    returns (None, None).

    Profit formula: sale_price + shipping_cost - ebay_fee - purchase_cost
    Margin formula: (profit / (sale_price + shipping_cost)) * 100
    """
    if purchase_cost is None:
        return None, None

    shipping = shipping_cost or Decimal("0")
    fee = ebay_fee or Decimal("0")

    profit = sale_price + shipping - fee - purchase_cost
    profit = Decimal(str(round(profit, 2)))

    revenue = sale_price + shipping
    if revenue > 0:
        margin_percent = (profit / revenue) * Decimal("100")
        margin_percent = Decimal(str(round(margin_percent, 2)))
    else:
        margin_percent = Decimal("0")

    return profit, margin_percent


async def get_order(db: AsyncSession, order_id: int) -> Optional[Order]:
    result = await db.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def get_order_with_product(db: AsyncSession, order_id: int) -> Optional[Order]:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.listing).selectinload(Listing.product))
    )
    return result.scalar_one_or_none()


async def get_order_by_ebay_id(db: AsyncSession, ebay_order_id: str) -> Optional[Order]:
    result = await db.execute(select(Order).where(Order.ebay_order_id == ebay_order_id))
    return result.scalar_one_or_none()


async def list_orders(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: Optional[OrderStatus] = None,
) -> List[Order]:
    query = select(Order)
    if status:
        query = query.where(Order.status == status)
    query = query.offset(skip).limit(limit).order_by(Order.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def process_order_webhook(
    db: AsyncSession,
    payload: OrderWebhookPayload,
) -> Order:
    """Create or update an Order from an eBay webhook payload.

    If the order already exists (matched by ebay_order_id), it is updated.
    Otherwise a new order is created.  When a new order is created and a
    matching listing is found via SKU, the listing's ``quantity_sold`` is
    incremented.
    """
    now = datetime.now(timezone.utc)

    # Resolve status
    try:
        order_status = OrderStatus(payload.status)
    except ValueError:
        logger.warning("Unknown order status '%s', defaulting to pending", payload.status)
        order_status = OrderStatus.pending

    # Try to find existing order
    existing = await get_order_by_ebay_id(db, payload.ebay_order_id)

    if existing:
        existing.buyer_username = payload.buyer_username or existing.buyer_username
        existing.sale_price = payload.sale_price
        existing.quantity = payload.quantity
        existing.shipping_cost = payload.shipping_cost or existing.shipping_cost
        existing.ebay_fee = payload.ebay_fee or existing.ebay_fee
        existing.status = order_status
        existing.shipping_address = payload.shipping_address or existing.shipping_address
        existing.payment_status = payload.payment_status or existing.payment_status
        existing.tracking_number = payload.tracking_number or existing.tracking_number
        existing.carrier = payload.carrier or existing.carrier
        existing.last_webhook_at = now
        if payload.raw_payload:
            existing.raw_payload = payload.raw_payload
        # Recalculate profit if purchase_cost is known
        if existing.purchase_cost is not None:
            existing.profit, existing.margin_percent = calculate_profit(
                existing.sale_price,
                existing.shipping_cost,
                existing.ebay_fee,
                existing.purchase_cost,
            )
        await db.commit()
        await db.refresh(existing)
        logger.info("Updated order %s from webhook", existing.ebay_order_id)
        return existing

    # Try to resolve listing by SKU
    listing_id = None
    if payload.sku:
        result = await db.execute(
            select(Listing).where(Listing.ebay_sku == payload.sku)
        )
        matched_listing = result.scalar_one_or_none()
        if matched_listing:
            listing_id = matched_listing.id
            # Increment quantity_sold on the listing
            matched_listing.quantity_sold = matched_listing.quantity_sold + payload.quantity
            # If quantity_sold reaches or exceeds quantity, mark as sold
            if matched_listing.quantity_sold >= matched_listing.quantity:
                matched_listing.status = ListingStatus.sold
            logger.info(
                "Linked webhook order %s to listing %s and incremented quantity_sold",
                payload.ebay_order_id,
                listing_id,
            )

    order = Order(
        ebay_order_id=payload.ebay_order_id,
        buyer_username=payload.buyer_username,
        sale_price=payload.sale_price,
        quantity=payload.quantity,
        shipping_cost=payload.shipping_cost,
        ebay_fee=payload.ebay_fee,
        status=order_status,
        listing_id=listing_id,
        shipping_address=payload.shipping_address,
        payment_status=payload.payment_status,
        tracking_number=payload.tracking_number,
        carrier=payload.carrier,
        raw_payload=payload.raw_payload,
        last_webhook_at=now,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    logger.info("Created order %s from webhook", order.ebay_order_id)
    return order


async def update_order_status(
    db: AsyncSession,
    order: Order,
    update: OrderStatusUpdate,
) -> Order:
    order.status = update.status
    if update.shipped_at is not None:
        order.shipped_at = update.shipped_at
    if update.delivered_at is not None:
        order.delivered_at = update.delivered_at
    await db.commit()
    await db.refresh(order)
    return order


async def update_order_fulfillment(
    db: AsyncSession,
    order: Order,
    update: OrderFulfillmentUpdate,
) -> Order:
    if update.tracking_number is not None:
        order.tracking_number = update.tracking_number
    if update.carrier is not None:
        order.carrier = update.carrier
    if update.shipped_at is not None:
        order.shipped_at = update.shipped_at
    if update.fulfillment_status is not None:
        order.fulfillment_status = update.fulfillment_status
    await db.commit()
    await db.refresh(order)
    return order


async def update_order(
    db: AsyncSession,
    order: Order,
    update: OrderUpdate,
) -> Order:
    """Update order fields from OrderUpdate schema."""
    update_data = update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(order, field, value)

    # Recalculate profit if purchase_cost is present
    if order.purchase_cost is not None:
        order.profit, order.margin_percent = calculate_profit(
            order.sale_price,
            order.shipping_cost,
            order.ebay_fee,
            order.purchase_cost,
        )
    elif "purchase_cost" in update_data and update_data["purchase_cost"] is None:
        order.profit = None
        order.margin_percent = None

    await db.commit()
    await db.refresh(order)
    return order


async def sync_orders_from_ebay(
    db: AsyncSession,
    api,
) -> dict:
    """Fetch orders from eBay API and create/update local records.

    *api* is an instance of EbayAPI (or compatible mock).
    Returns a dict with processed, succeeded, and failed counts.
    """
    ebay_orders = await api.get_orders(limit=50)

    processed = 0
    succeeded = 0
    failed = 0

    for ebay_order in ebay_orders:
        processed += 1
        try:
            ebay_order_id = ebay_order.get("orderId")
            if not ebay_order_id:
                failed += 1
                continue

            result = await db.execute(
                select(Order).where(Order.ebay_order_id == ebay_order_id)
            )
            existing = result.scalar_one_or_none()

            buyer = ebay_order.get("buyer", {})
            buyer_username = buyer.get("username")

            fulfillment = ebay_order.get("orderFulfillmentStatus", "NOT_STARTED")
            order_status = OrderStatus.pending
            if fulfillment == "FULFILLED":
                order_status = OrderStatus.shipped
            elif fulfillment == "CANCELLED":
                order_status = OrderStatus.cancelled

            line_items = ebay_order.get("lineItems", [])
            if not line_items:
                failed += 1
                continue

            line_item = line_items[0]
            cost = line_item.get("lineItemCost", {}) or {}
            sale_price = Decimal(str(cost.get("value", "0")))
            quantity = line_item.get("quantity", 1)

            sku = line_item.get("sku")
            listing_id = None
            if sku:
                result = await db.execute(
                    select(Listing).where(Listing.ebay_sku == sku)
                )
                matched_listing = result.scalar_one_or_none()
                if matched_listing:
                    listing_id = matched_listing.id

            if existing:
                existing.buyer_username = buyer_username
                existing.status = order_status
                existing.sale_price = sale_price
                existing.quantity = quantity
                if listing_id:
                    existing.listing_id = listing_id
                # Recalculate profit if we have purchase_cost
                if existing.purchase_cost is not None:
                    existing.profit, existing.margin_percent = calculate_profit(
                        existing.sale_price,
                        existing.shipping_cost,
                        existing.ebay_fee,
                        existing.purchase_cost,
                    )
            else:
                order = Order(
                    ebay_order_id=ebay_order_id,
                    buyer_username=buyer_username,
                    sale_price=sale_price,
                    quantity=quantity,
                    status=order_status,
                    listing_id=listing_id,
                )
                db.add(order)

            succeeded += 1
        except Exception as exc:
            logger.error(
                "Failed to sync order %s: %s",
                ebay_order.get("orderId"),
                exc,
            )
            failed += 1

    await db.commit()

    return {"processed": processed, "succeeded": succeeded, "failed": failed}


async def record_purchase(
    db: AsyncSession,
    order: Order,
    purchase: OrderPurchase,
) -> Order:
    """Record Amazon purchase details on an order and recalculate profit."""
    update_data = purchase.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(order, field, value)

    order.purchased_at = datetime.now(timezone.utc)

    # Recalculate profit with the new purchase_cost
    order.profit, order.margin_percent = calculate_profit(
        order.sale_price,
        order.shipping_cost,
        order.ebay_fee,
        order.purchase_cost,
    )

    await db.commit()
    await db.refresh(order)
    return order
