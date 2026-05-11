from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import product_service
from app.schemas.schemas import ProductOut, ProductCreate

router = APIRouter()


@router.get("/", response_model=List[ProductOut])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    products = await product_service.list_products(db, skip=skip, limit=limit, category=category, is_active=is_active)
    return products


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/asin/{asin}", response_model=ProductOut)
async def get_product_by_asin(asin: str, db: AsyncSession = Depends(get_db)):
    product = await product_service.get_product_by_asin(db, asin)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/", response_model=ProductOut, status_code=201)
async def create_product(product_in: ProductCreate, db: AsyncSession = Depends(get_db)):
    existing = await product_service.get_product_by_asin(db, product_in.asin)
    if existing:
        raise HTTPException(status_code=409, detail="Product with this ASIN already exists")
    return await product_service.create_product(db, product_in)