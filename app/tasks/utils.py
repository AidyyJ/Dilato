import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Coroutine, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.resilience import calculate_backoff
from app.models.models import SyncLog, SyncStatus, SyncType

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a synchronous Celery task."""
    return asyncio.run(coro)


def get_celery_retry_countdown(task_self) -> int:
    """Return an exponential-backoff countdown for a Celery retry.

    Uses the task's current retry attempt (0-indexed) to compute delay.
    """
    attempt = task_self.request.retries
    delay = calculate_backoff(
        attempt,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=True,
    )
    return max(1, int(delay))


@asynccontextmanager
async def task_session():
    """Provide an async DB session for Celery tasks."""
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


async def create_sync_log(session: AsyncSession, sync_type: SyncType) -> SyncLog:
    log = SyncLog(
        sync_type=sync_type,
        status=SyncStatus.running,
        started_at=datetime.utcnow(),
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def complete_sync_log(
    session: AsyncSession,
    log: SyncLog,
    status: SyncStatus,
    processed: int = 0,
    succeeded: int = 0,
    failed: int = 0,
    error_message: str = None,
) -> None:
    log.status = status
    log.records_processed = processed
    log.records_succeeded = succeeded
    log.records_failed = failed
    log.error_message = error_message
    log.completed_at = datetime.utcnow()
    await session.commit()
