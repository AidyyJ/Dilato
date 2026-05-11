import logging
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.amazon_api import amazon_api
from app.services.product_service import upsert_product_from_amazon
from app.services import pricing_service
from app.services import listing_creator
from app.schemas.schemas import SourcingResult

logger = logging.getLogger(__name__)


async def search_and_source(
    db: AsyncSession,
    keywords: Optional[List[str]] = None,
    category: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    min_margin: Optional[float] = None,
    max_results: int = 50,
    auto_create_listings: bool = False,
) -> List[SourcingResult]:
    """Search Amazon products and evaluate profit margins against eBay prices.

    TODO: Full implementation after Backend Engineer completes Amazon and eBay API clients.
    Current version returns NotImplementedError from amazon_api.search_items().

    Algorithm:
    1. Search Amazon PA-API for matching products
    2. Filter by price range
    3. For each product, estimate eBay selling price (via completed listings or category averages)
    4. Calculate margin = (ebay_price - amazon_price - ebay_fee) / ebay_price
    5. Return products meeting the minimum margin threshold
    """
    min_margin = min_margin or settings.DEFAULT_PROFIT_MARGIN_THRESHOLD
    if max_price is None:
        max_price = Decimal(str(settings.DEFAULT_MAX_PRICE_USD))
    if min_price is None:
        min_price = Decimal(str(settings.DEFAULT_MIN_PRICE_USD))

    keyword_str = " ".join(keywords) if keywords else None
    raw_items = await amazon_api.search_items(
        keywords=keyword_str,
        browse_node_id=category,
        item_count=max_results,
    )

    results: List[SourcingResult] = []
    for item in raw_items:
        raw_price = item.get("price")
        if raw_price is None:
            continue
        amazon_price = Decimal(str(raw_price))
        if not (min_price <= amazon_price <= max_price):
            continue

        asin = item.get("asin", "")
        title = item.get("title", "")
        image_url = item.get("image_url")
        estimated_ebay_price = await _estimate_ebay_price(db, asin, amazon_price)

        margin = None
        if estimated_ebay_price and estimated_ebay_price > 0:
            fee = estimated_ebay_price * Decimal("0.13")
            margin = float((estimated_ebay_price - amazon_price - fee) / estimated_ebay_price)
            if margin < min_margin:
                continue

        product = await upsert_product_from_amazon(
            db, asin=asin, title=title,
            category=category, image_url=image_url,
            amazon_price=amazon_price,
            detail_page_url=item.get("detail_page_url"),
        )

        if auto_create_listings:
            try:
                await listing_creator.create_listing_from_product(db, product.id)
            except ValueError as exc:
                logger.warning(
                    "Auto-listing creation failed for product %s: %s",
                    product.id,
                    exc,
                )

        results.append(SourcingResult(
            asin=asin,
            title=title,
            amazon_price=amazon_price,
            estimated_ebay_price=estimated_ebay_price,
            estimated_margin=margin,
            category=category,
            image_url=image_url,
        ))

    return results


async def _estimate_ebay_price(
    db: AsyncSession,
    asin: str,
    amazon_price: Decimal,
) -> Optional[Decimal]:
    """Estimate the potential eBay selling price for a product.

    Uses the pricing rules engine. Falls back to a 1.30x markup if no rules match.
    """
    rules = await pricing_service.get_active_rules(db)
    estimated = pricing_service.apply_best_rule(amazon_price, None, rules)
    if estimated is not None:
        return estimated
    return (amazon_price * Decimal("1.30")).quantize(Decimal("0.01"))