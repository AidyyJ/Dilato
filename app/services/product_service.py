import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Product, ProductSource
from app.schemas.schemas import ProductCreate

logger = logging.getLogger(__name__)


async def get_product(db: AsyncSession, product_id: int) -> Optional[Product]:
    result = await db.execute(select(Product).where(Product.id == product_id))
    return result.scalar_one_or_none()


async def get_product_by_asin(db: AsyncSession, asin: str) -> Optional[Product]:
    result = await db.execute(select(Product).where(Product.asin == asin))
    return result.scalar_one_or_none()


async def list_products(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Product]:
    query = select(Product)
    if category:
        query = query.where(Product.category == category)
    if is_active is not None:
        query = query.where(Product.is_active == is_active)
    query = query.offset(skip).limit(limit).order_by(Product.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_product(db: AsyncSession, product_in: ProductCreate) -> Product:
    product = Product(
        asin=product_in.asin,
        title=product_in.title,
        brand=product_in.brand,
        category=product_in.category,
        image_url=product_in.image_url,
        detail_page_url=product_in.detail_page_url,
        amazon_price=product_in.amazon_price,
        current_price=product_in.current_price,
        source=ProductSource.amazon,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def upsert_product_from_amazon(
    db: AsyncSession,
    asin: str,
    title: str,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    image_url: Optional[str] = None,
    detail_page_url: Optional[str] = None,
    amazon_price: Optional[Decimal] = None,
) -> Product:
    existing = await get_product_by_asin(db, asin)
    if existing:
        existing.title = title
        existing.brand = brand
        existing.category = category
        existing.image_url = image_url
        existing.detail_page_url = detail_page_url
        existing.amazon_price = amazon_price
        existing.current_price = amazon_price
        existing.last_synced_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    product = Product(
        asin=asin,
        title=title,
        brand=brand,
        category=category,
        image_url=image_url,
        detail_page_url=detail_page_url,
        amazon_price=amazon_price,
        current_price=amazon_price,
        source=ProductSource.amazon,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product