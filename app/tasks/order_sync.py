import logging

from app.tasks.celery_app import celery_app
from app.tasks.utils import run_async, task_session, create_sync_log, complete_sync_log, get_celery_retry_countdown
from app.services.ebay_api import EbayAPI
from app.services import order_service
from app.models.models import SyncStatus, SyncType

logger = logging.getLogger(__name__)


async def _sync_ebay_orders() -> dict:
    async with task_session() as session:
        log = await create_sync_log(session, SyncType.ebay_order)
        api = EbayAPI()
        try:
            result = await order_service.sync_orders_from_ebay(session, api)
            await complete_sync_log(
                session,
                log,
                SyncStatus.completed,
                processed=result.get("processed", 0),
                succeeded=result.get("succeeded", 0),
                failed=result.get("failed", 0),
            )
            return result
        except Exception as exc:
            logger.exception("eBay order sync failed")
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
def sync_ebay_orders(self):
    """Celery task to sync eBay orders."""
    logger.info("Starting eBay order sync")
    try:
        return run_async(_sync_ebay_orders())
    except Exception as exc:
        logger.exception("eBay order sync task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))
