import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.tasks.utils import run_async, task_session, create_sync_log, complete_sync_log, get_celery_retry_countdown
from app.models.models import Product, Listing, ListingStatus, SyncStatus, SyncType
from app.services.amazon_api import AmazonProductAPI
from app.services.ebay_api import EbayAPI
from app.core.config import settings

logger = logging.getLogger(__name__)


async def _sync_amazon_stock() -> dict:
    async with task_session() as session:
        log = await create_sync_log(session, SyncType.stock_sync)
        amazon_api = AmazonProductAPI()
        try:
            result = await session.execute(select(Product))
            products = list(result.scalars().all())

            if not products:
                await complete_sync_log(session, log, SyncStatus.completed, processed=0)
                return {"processed": 0, "succeeded": 0, "failed": 0}

            # Pre-load active listings into a map by product_id
            listings_result = await session.execute(
                select(Listing).where(Listing.status == ListingStatus.active)
            )
            all_active_listings = list(listings_result.scalars().all())
            listing_map: dict[int, list[Listing]] = {}
            for listing in all_active_listings:
                listing_map.setdefault(listing.product_id, []).append(listing)

            chunk_size = 10
            succeeded = 0
            failed = 0
            total_processed = 0

            for i in range(0, len(products), chunk_size):
                chunk = products[i : i + chunk_size]
                chunk_asins = [p.asin for p in chunk]
                try:
                    items = await amazon_api.get_items(chunk_asins)
                    item_map = {
                        item["asin"]: item for item in items if item.get("asin")
                    }
                except Exception as exc:
                    logger.error(
                        "Failed to fetch Amazon items for chunk %s: %s",
                        chunk_asins,
                        exc,
                    )
                    failed += len(chunk)
                    total_processed += len(chunk)
                    continue

                ebay_api = EbayAPI()
                try:
                    for product in chunk:
                        try:
                            item = item_map.get(product.asin)
                            available = item is not None

                            if product.is_active != available:
                                product.is_active = available

                            listings = listing_map.get(product.id, [])
                            product_failed = 0
                            if available:
                                for listing in listings:
                                    if listing.quantity != settings.DEFAULT_AVAILABLE_QUANTITY:
                                        sku = listing.ebay_sku or f"LISTING-{listing.id}"
                                        try:
                                            await ebay_api.update_listing(
                                                sku,
                                                {"quantity": settings.DEFAULT_AVAILABLE_QUANTITY},
                                            )
                                            listing.quantity = settings.DEFAULT_AVAILABLE_QUANTITY
                                        except Exception as exc:
                                            logger.error(
                                                "Failed to update eBay listing quantity for %s: %s",
                                                sku,
                                                exc,
                                            )
                                            product_failed += 1
                            else:
                                for listing in listings:
                                    sku = listing.ebay_sku or f"LISTING-{listing.id}"
                                    try:
                                        await ebay_api.end_listing(sku)
                                        listing.status = ListingStatus.ended
                                        listing.ended_at = (
                                            datetime.now(timezone.utc).replace(tzinfo=None)
                                        )
                                    except Exception as exc:
                                        logger.error(
                                            "Failed to end eBay listing for %s: %s",
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
                                "Failed to sync stock for product %s: %s",
                                product.asin,
                                exc,
                            )
                            failed += 1
                finally:
                    await ebay_api.close()

                total_processed += len(chunk)
                if i + chunk_size < len(products):
                    await asyncio.sleep(1)

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
        except Exception as exc:
            logger.exception("Amazon stock sync failed")
            await complete_sync_log(
                session,
                log,
                SyncStatus.failed,
                error_message=str(exc),
            )
            raise
        finally:
            await amazon_api.close()


@celery_app.task(bind=True, name="tasks.sync_amazon_stock", max_retries=3)
def sync_amazon_stock(self):
    """Celery task to sync Amazon stock availability with eBay listings."""
    logger.info("Starting Amazon stock sync")
    try:
        return run_async(_sync_amazon_stock())
    except Exception as exc:
        logger.exception("Amazon stock sync task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))
