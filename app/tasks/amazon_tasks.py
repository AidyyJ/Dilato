import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.tasks.utils import run_async, task_session, create_sync_log, complete_sync_log, get_celery_retry_countdown
from app.models.models import Product, PriceHistory, SyncStatus, SyncType
from app.services.amazon_api import AmazonProductAPI
from app.services.product_service import upsert_product_from_amazon

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Amazon product sync
# ---------------------------------------------------------------------------

async def _sync_amazon_products(
    keywords: Optional[str] = None,
    browse_node_id: Optional[str] = None,
) -> dict:
    async with task_session() as session:
        log = await create_sync_log(session, SyncType.amazon_product)
        api = AmazonProductAPI()
        try:
            items = await api.search_items(
                keywords=keywords,
                browse_node_id=browse_node_id,
                item_count=10,
            )

            succeeded = 0
            failed = 0
            for item in items:
                try:
                    await upsert_product_from_amazon(
                        session,
                        asin=item["asin"],
                        title=item["title"],
                        brand=item.get("brand"),
                        category=item.get("category"),
                        image_url=item.get("image_url"),
                        detail_page_url=item.get("detail_page_url"),
                        amazon_price=item.get("price"),
                    )
                    succeeded += 1
                except Exception as exc:  # pragma: no cover
                    logger.error(
                        "Failed to upsert product %s: %s",
                        item.get("asin"),
                        exc,
                    )
                    failed += 1

            await complete_sync_log(
                session,
                log,
                SyncStatus.completed,
                processed=len(items),
                succeeded=succeeded,
                failed=failed,
            )
            return {"processed": len(items), "succeeded": succeeded, "failed": failed}
        except Exception as exc:
            logger.exception("Amazon product sync failed")
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
def sync_amazon_products(
    self,
    keywords: str = None,
    browse_node_id: str = None,
):
    """Celery task to sync Amazon products via PA-API."""
    logger.info(
        "Starting Amazon product sync: keywords=%s, browse_node_id=%s",
        keywords,
        browse_node_id,
    )
    try:
        return run_async(_sync_amazon_products(keywords, browse_node_id))
    except Exception as exc:
        logger.exception("Amazon product sync task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))


# ---------------------------------------------------------------------------
# Amazon price refresh
# ---------------------------------------------------------------------------

async def _refresh_amazon_prices() -> dict:
    async with task_session() as session:
        log = await create_sync_log(session, SyncType.price_refresh)
        api = AmazonProductAPI()
        try:
            result = await session.execute(
                select(Product)
                .where(Product.is_active.is_(True))
                .order_by(Product.last_synced_at.asc().nullsfirst())
                .limit(100)
            )
            products = list(result.scalars().all())

            if not products:
                await complete_sync_log(session, log, SyncStatus.completed, processed=0)
                return {"processed": 0, "succeeded": 0, "failed": 0}

            asins = [p.asin for p in products]
            chunk_size = 10
            succeeded = 0
            failed = 0
            total_processed = 0

            for i in range(0, len(asins), chunk_size):
                chunk = asins[i : i + chunk_size]
                try:
                    items = await api.get_items(chunk)
                    for item in items:
                        product = next(
                            (p for p in products if p.asin == item["asin"]),
                            None,
                        )
                        if not product:
                            continue

                        new_price = item.get("price")
                        if new_price is not None:
                            new_price_dec = Decimal(str(new_price))
                            if product.current_price != new_price_dec:
                                history = PriceHistory(
                                    product_id=product.id,
                                    price=new_price_dec,
                                    currency=item.get("currency", "USD"),
                                    source="amazon",
                                )
                                session.add(history)
                                product.amazon_price = new_price_dec
                                product.current_price = new_price_dec

                        product.last_synced_at = datetime.utcnow()
                        succeeded += 1
                    await session.commit()
                except Exception as exc:  # pragma: no cover
                    logger.error(
                        "Failed to refresh prices for chunk %s: %s",
                        chunk,
                        exc,
                    )
                    failed += len(chunk)
                total_processed += len(chunk)

            await complete_sync_log(
                session,
                log,
                SyncStatus.completed,
                processed=len(products),
                succeeded=succeeded,
                failed=failed,
            )
            return {"processed": len(products), "succeeded": succeeded, "failed": failed}
        except Exception as exc:
            logger.exception("Amazon price refresh failed")
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
def refresh_amazon_prices(self):
    """Celery task to refresh Amazon prices for tracked products."""
    logger.info("Starting Amazon price refresh")
    try:
        return run_async(_refresh_amazon_prices())
    except Exception as exc:
        logger.exception("Amazon price refresh task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))
