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
    PriceHistory,
    SyncStatus,
    SyncType,
)
from app.services.ebay_api import EbayAPI
from app.services import pricing_service
from app.core.config import settings

logger = logging.getLogger(__name__)


async def _sync_amazon_prices() -> dict:
    async with task_session() as session:
        log = await create_sync_log(session, SyncType.price_sync)
        try:
            # Fetch active eBay listings and their products
            listings_result = await session.execute(
                select(Listing).where(Listing.status == ListingStatus.active)
            )
            listings = list(listings_result.scalars().all())
            product_ids = {l.product_id for l in listings}

            if not product_ids:
                await complete_sync_log(session, log, SyncStatus.completed, processed=0)
                return {"processed": 0, "succeeded": 0, "failed": 0}

            products_result = await session.execute(
                select(Product)
                .where(Product.id.in_(product_ids), Product.is_active.is_(True))
            )
            products = list(products_result.scalars().all())
            product_map = {p.id: p for p in products}

            listing_map: dict[int, list[Listing]] = {}
            for listing in listings:
                listing_map.setdefault(listing.product_id, []).append(listing)

            rules = await pricing_service.get_active_rules(session)

            ebay_api = EbayAPI()
            try:
                succeeded = 0
                failed = 0
                total_processed = 0

                for product in products:
                    total_processed += 1
                    try:
                        new_price = await pricing_service.calculate_listing_price(
                            session, product, rules=rules
                        )
                        if new_price is None:
                            succeeded += 1
                            continue

                        product_listings = listing_map.get(product.id, [])
                        product_failed = 0
                        for listing in product_listings:
                            old_price = listing.listing_price
                            should_update = False
                            if old_price is None or old_price == 0:
                                should_update = True
                            else:
                                delta_pct = (
                                    abs(new_price - old_price)
                                    / old_price
                                    * Decimal("100")
                                )
                                if delta_pct > Decimal(
                                    str(settings.PRICE_SYNC_MIN_DELTA_PERCENT)
                                ):
                                    should_update = True

                            if should_update:
                                sku = listing.ebay_sku or f"LISTING-{listing.id}"
                                try:
                                    await ebay_api.update_listing(
                                        sku,
                                        {
                                            "price": str(new_price),
                                            "currency": "USD",
                                        },
                                    )
                                    # Record price history and update DB only after eBay succeeds
                                    history = PriceHistory(
                                        product_id=product.id,
                                        price=new_price,
                                        currency="USD",
                                        source="ebay",
                                    )
                                    session.add(history)
                                    listing.listing_price = new_price
                                except Exception as exc:
                                    logger.error(
                                        "Failed to update eBay listing price for %s: %s",
                                        sku,
                                        exc,
                                    )
                                    product_failed += 1

                        if product_failed > 0:
                            failed += 1
                        else:
                            succeeded += 1
                    except Exception as exc:
                        logger.error(
                            "Failed to sync price for product %s: %s",
                            product.asin,
                            exc,
                        )
                        failed += 1

                await session.commit()

                await complete_sync_log(
                    session,
                    log,
                    SyncStatus.completed,
                    processed=total_processed,
                    succeeded=succeeded,
                    failed=failed,
                )
                return {
                    "processed": total_processed,
                    "succeeded": succeeded,
                    "failed": failed,
                }
            finally:
                await ebay_api.close()
        except Exception as exc:
            logger.exception("Amazon price sync failed")
            await complete_sync_log(
                session,
                log,
                SyncStatus.failed,
                error_message=str(exc),
            )
            raise


@celery_app.task(bind=True, name="tasks.sync_amazon_prices", max_retries=3)
def sync_amazon_prices(self):
    """Celery task to sync Amazon prices with eBay listings using pricing rules."""
    logger.info("Starting Amazon price sync")
    try:
        return run_async(_sync_amazon_prices())
    except Exception as exc:
        logger.exception("Amazon price sync task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))
