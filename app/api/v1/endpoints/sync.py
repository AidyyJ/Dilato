from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import SyncLog, SyncType
from app.schemas.schemas import SyncLogOut
from app.tasks.stock_sync import sync_amazon_stock
from app.tasks.price_sync import sync_amazon_prices

router = APIRouter()


@router.post("/stock", status_code=202)
async def trigger_stock_sync():
    """Trigger a manual stock sync task."""
    task = sync_amazon_stock.delay()
    return {"task_id": task.id, "status": "queued"}


@router.post("/prices", status_code=202)
async def trigger_price_sync():
    """Trigger a manual price sync task."""
    task = sync_amazon_prices.delay()
    return {"task_id": task.id, "status": "queued"}


@router.get("/status")
async def get_sync_status(db: AsyncSession = Depends(get_db)):
    """Get the last sync status for each sync type."""
    result = {}
    for sync_type in SyncType:
        log_result = await db.execute(
            select(SyncLog)
            .where(SyncLog.sync_type == sync_type)
            .order_by(SyncLog.created_at.desc())
            .limit(1)
        )
        log = log_result.scalar_one_or_none()
        result[sync_type.value] = (
            SyncLogOut.model_validate(log) if log else None
        )
    return result
