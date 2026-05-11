import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Listing, ListingStatus
from app.schemas.schemas import ListingCreate

logger = logging.getLogger(__name__)


async def get_listing(db: AsyncSession, listing_id: int) -> Optional[Listing]:
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    return result.scalar_one_or_none()


async def list_listings(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: Optional[ListingStatus] = None,
) -> List[Listing]:
    query = select(Listing)
    if status:
        query = query.where(Listing.status == status)
    query = query.offset(skip).limit(limit).order_by(Listing.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_listing(db: AsyncSession, listing_in: ListingCreate) -> Listing:
    listing = Listing(
        product_id=listing_in.product_id,
        title=listing_in.title,
        listing_price=listing_in.listing_price,
        quantity=listing_in.quantity,
        ebay_category_id=listing_in.ebay_category_id,
        listing_duration=listing_in.listing_duration,
        status=ListingStatus.draft,
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return listing


async def update_listing_status(
    db: AsyncSession,
    listing_id: int,
    status: ListingStatus,
    ebay_item_id: Optional[str] = None,
) -> Optional[Listing]:
    listing = await get_listing(db, listing_id)
    if not listing:
        return None
    listing.status = status
    if ebay_item_id:
        listing.ebay_item_id = ebay_item_id
    if status == ListingStatus.active and not listing.started_at:
        listing.started_at = datetime.now(timezone.utc)
    if status == ListingStatus.ended:
        listing.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(listing)
    return listing