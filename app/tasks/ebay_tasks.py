import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.tasks.utils import run_async, task_session, create_sync_log, complete_sync_log, get_celery_retry_countdown
from app.models.models import (
    Product,
    Listing,
    ListingStatus,
    SyncStatus,
    SyncType,
)
from app.services.ebay_api import EbayAPI
from app.services import pricing_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# eBay listing sync
# ---------------------------------------------------------------------------

async def _sync_ebay_listings() -> dict:
    async with task_session() as session:
        log = await create_sync_log(session, SyncType.ebay_listing)
        api = EbayAPI()
        try:
            result = await session.execute(
                select(Listing).where(
                    Listing.status.in_([ListingStatus.active, ListingStatus.ended])
                )
            )
            listings = list(result.scalars().all())

            processed = 0
            succeeded = 0
            failed = 0

            for listing in listings:
                processed += 1
                try:
                    sku = listing.ebay_sku or f"LISTING-{listing.id}"
                    offer = await api._find_offer_by_sku(sku)

                    if listing.status == ListingStatus.active and not offer:
                        listing.status = ListingStatus.ended
                        listing.ended_at = datetime.utcnow()
                    elif listing.status == ListingStatus.ended and offer:
                        listing.status = ListingStatus.active
                        listing.started_at = datetime.utcnow()

                    succeeded += 1
                except Exception as exc:  # pragma: no cover
                    logger.error(
                        "Failed to sync listing %s: %s",
                        listing.id,
                        exc,
                    )
                    failed += 1

            await session.commit()

            await complete_sync_log(
                session,
                log,
                SyncStatus.completed,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
            )
            return {"processed": processed, "succeeded": succeeded, "failed": failed}
        except Exception as exc:
            logger.exception("eBay listing sync failed")
            await complete_sync_log(
                session,
                log,
                SyncStatus.failed,
                error_message=str(exc),
            )
            raise
        finally:
            await api.close()


@celery_app.task(bind=True, max_retries=3)
def sync_ebay_listings(self):
    """Celery task to sync eBay listings status."""
    logger.info("Starting eBay listing sync")
    try:
        return run_async(_sync_ebay_listings())
    except Exception as exc:
        logger.exception("eBay listing sync task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))


# ---------------------------------------------------------------------------
# Publish eBay listing
# ---------------------------------------------------------------------------

async def _publish_ebay_listing(listing_id: int) -> dict:
    async with task_session() as session:
        result = await session.execute(
            select(Listing).where(Listing.id == listing_id)
        )
        listing = result.scalar_one_or_none()
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")

        result = await session.execute(
            select(Product).where(Product.id == listing.product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            raise ValueError(f"Product for listing {listing_id} not found")

        # Always calculate listing price via pricing service so the latest
        # rules are applied at publish time.
        calculated = await pricing_service.calculate_listing_price(session, product)
        if calculated is not None:
            price = calculated
            listing.listing_price = price
        else:
            price = listing.listing_price

        # Fallback chain if the resolved price is missing or invalid.
        if price is None or price <= 0:
            fallback_price = product.current_price or product.amazon_price
            if fallback_price is not None and fallback_price > 0:
                logger.warning(
                    "Price fallback used for listing %s: calculated/listing price "
                    "(%s) invalid, falling back to product price (%s)",
                    listing_id,
                    price,
                    fallback_price,
                )
                price = fallback_price
                listing.listing_price = price
            else:
                logger.error(
                    "Cannot publish listing %s: no valid price available "
                    "(calculated/listing=%s, current=%s, amazon=%s)",
                    listing_id,
                    price,
                    product.current_price,
                    product.amazon_price,
                )
                raise ValueError(
                    f"Cannot publish listing {listing_id}: no valid price available"
                )

        api = EbayAPI()
        try:
            sku = listing.ebay_sku or f"LISTING-{listing.id}"
            listing_data = {
                "sku": sku,
                "title": listing.title,
                "description": product.title or listing.title,
                "brand": product.brand,
                "image_urls": [product.image_url] if product.image_url else [],
                "condition": "NEW",
                "quantity": listing.quantity,
                "price": str(price),
                "currency": "USD",
                "category_id": listing.ebay_category_id or "",
                "listing_duration": listing.listing_duration or "GTC",
            }

            result = await api.create_listing(listing_data)

            listing.status = ListingStatus.active
            listing.ebay_item_id = result.get("item_id")
            listing.ebay_sku = sku
            listing.started_at = datetime.utcnow()
            await session.commit()

            return {
                "listing_id": listing.id,
                "ebay_item_id": result.get("item_id"),
                "status": "active",
            }
        finally:
            await api.close()


@celery_app.task(bind=True, max_retries=3)
def publish_ebay_listing(self, listing_id: int):
    """Celery task to publish a listing to eBay."""
    logger.info("Publishing eBay listing: listing_id=%s", listing_id)
    try:
        return run_async(_publish_ebay_listing(listing_id))
    except Exception as exc:
        logger.exception("eBay listing publish task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))
