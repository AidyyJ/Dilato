import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sourcing_service import search_and_source
from app.schemas.schemas import SourcingRequest, SourcingResult

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=List[SourcingResult])
async def sourcing_search(request: SourcingRequest, db: AsyncSession = Depends(get_db)):
    try:
        results = await search_and_source(
            db,
            keywords=request.keywords,
            category=request.category,
            min_price=request.min_price,
            max_price=request.max_price,
            min_margin=request.min_margin,
            max_results=request.max_results,
            auto_create_listings=request.auto_create_listings,
        )
        return results
    except Exception as exc:
        logger.exception("Sourcing search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sourcing search failed: {exc}",
        )