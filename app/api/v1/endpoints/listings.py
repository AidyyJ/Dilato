from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import ListingStatus
from app.services import listing_service
from app.services import listing_creator
from app.services import product_service
from app.services import pricing_service
from app.services.ebay_api import EbayAPIError
from app.schemas.schemas import (
    ListingOut,
    ListingCreate,
    ListingCreateFromProduct,
    ListingPublishOut,
)

router = APIRouter()


@router.get("/", response_model=List[ListingOut])
async def list_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[ListingStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    listings = await listing_service.list_listings(db, skip=skip, limit=limit, status=status)
    return listings


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(listing_id: int, db: AsyncSession = Depends(get_db)):
    listing = await listing_service.get_listing(db, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("/", response_model=ListingOut, status_code=201)
async def create_listing(listing_in: ListingCreate, db: AsyncSession = Depends(get_db)):
    # Auto-calculate price if omitted and a valid product is referenced.
    listing_price = listing_in.listing_price
    if listing_price is None:
        product = await product_service.get_product(db, listing_in.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        calculated = await pricing_service.calculate_listing_price(db, product)
        if calculated is None:
            raise HTTPException(
                status_code=422,
                detail="Unable to calculate listing price for product; provide listing_price explicitly",
            )
        listing_price = calculated

    # Build a new ListingCreate with the resolved price.
    data = listing_in.model_dump()
    data["listing_price"] = listing_price
    resolved = ListingCreate(**data)
    return await listing_service.create_listing(db, resolved)


@router.post("/create-from-product", response_model=ListingOut, status_code=201)
async def create_listing_from_product(
    payload: ListingCreateFromProduct,
    db: AsyncSession = Depends(get_db),
):
    try:
        listing = await listing_creator.create_listing_from_product(
            db, payload.product_id, payload.pricing_rule_id
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=422, detail=detail)
    return listing


@router.post("/{listing_id}/publish", response_model=ListingOut)
async def publish_listing(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        listing = await listing_creator.publish_listing(db, listing_id)
    except ValueError as exc:
        # Distinguish between not-found and bad-state errors.
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=422, detail=detail)
    except EbayAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return listing


@router.post("/create-and-publish", response_model=ListingOut, status_code=201)
async def create_and_publish_listing(
    payload: ListingCreateFromProduct,
    db: AsyncSession = Depends(get_db),
):
    try:
        listing = await listing_creator.create_and_publish_listing(
            db, payload.product_id, payload.pricing_rule_id
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=422, detail=detail)
    except EbayAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return listing


@router.patch("/{listing_id}/status", response_model=ListingOut)
async def update_listing_status(
    listing_id: int,
    status: ListingStatus,
    ebay_item_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    listing = await listing_service.update_listing_status(db, listing_id, status, ebay_item_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing
