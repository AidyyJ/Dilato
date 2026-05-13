import logging
from typing import List, Optional

from app.tasks.celery_app import celery_app
from app.tasks.utils import run_async, task_session, get_celery_retry_countdown
from app.services.sourcing_service import search_and_source

logger = logging.getLogger(__name__)


async def _run_sourcing_scan(
    keywords: Optional[List[str]] = None,
    category: Optional[str] = None,
    max_results: int = 50,
) -> dict:
    async with task_session() as session:
        results = await search_and_source(
            session,
            keywords=keywords,
            category=category,
            max_results=max_results,
        )
        return {
            "found": len(results),
            "results": [r.model_dump() for r in results],
        }


@celery_app.task(bind=True, max_retries=3)
def run_sourcing_scan(
    self,
    keywords: list = None,
    category: str = None,
    max_results: int = 50,
):
    """Celery task to run a product sourcing scan."""
    logger.info(
        "Starting sourcing scan: keywords=%s, category=%s, max_results=%s",
        keywords,
        category,
        max_results,
    )
    try:
        return run_async(_run_sourcing_scan(keywords, category, max_results))
    except Exception as exc:
        logger.exception("Sourcing scan task failed")
        raise self.retry(exc=exc, countdown=get_celery_retry_countdown(self))
