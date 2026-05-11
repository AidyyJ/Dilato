import html
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Listing, ListingStatus, Product
from app.services.ebay_api import EbayAPI
from app.services import pricing_service
from app.services.product_service import get_product

logger = logging.getLogger(__name__)

# Common eBay restricted / policy-sensitive words to scrub from titles.
_EBAY_RESTRICTED_WORDS = {
    "prohibited",
    "banned",
    "counterfeit",
    "replica",
    "fake",
    "knockoff",
    "unauthorized",
    "pirated",
    "torrent",
    "drm",
    "jailbroken",
    "modded",
    "region free",
    "cd key",
    "oem",
}

_EBAY_TITLE_MAX_LENGTH = 80

_ALLOWED_URL_SCHEMES = {"http", "https"}


def _is_safe_url(url: Optional[str]) -> bool:
    """Return True if ``url`` uses an allowed scheme (http/https)."""
    if not url:
        return False
    try:
        scheme = urlparse(url).scheme.lower()
    except Exception:
        return False
    return scheme in _ALLOWED_URL_SCHEMES


def _scrub_restricted_words(text: str) -> str:
    """Remove known eBay policy-sensitive words (case-insensitive)."""
    lowered = text.lower()
    for word in _EBAY_RESTRICTED_WORDS:
        # Whole-word replacement to avoid mangling innocent substrings.
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        text = pattern.sub("", text)
    # Collapse multiple spaces left behind
    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_listing_title(product: Product) -> str:
    """Transform an Amazon product title into an eBay-compliant title.

    - Removes restricted words.
    - Truncates to eBay's 80-character limit at a word boundary when possible.
    - Falls back to the product ASIN or a generic title if the result is empty.
    """
    raw = product.title or ""
    clean = _scrub_restricted_words(raw)

    if not clean:
        clean = product.asin or "Untitled Listing"

    if len(clean) <= _EBAY_TITLE_MAX_LENGTH:
        return clean

    # Truncate at the last space before the limit to avoid cutting words.
    truncated = clean[:_EBAY_TITLE_MAX_LENGTH]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]

    return truncated.strip()


def generate_listing_description(product: Product, listing_price: Decimal) -> str:
    """Build an HTML description for an eBay listing from product data."""
    title = html.escape(product.title or "N/A")
    brand = html.escape(product.brand) if product.brand else None
    category = html.escape(product.category) if product.category else None
    raw_detail_url = product.detail_page_url
    detail_url = html.escape(raw_detail_url) if raw_detail_url else None
    if raw_detail_url and not _is_safe_url(raw_detail_url):
        logger.warning(
            "Unsafe URL scheme in detail_page_url for product %s: %s",
            product.id,
            raw_detail_url,
        )
        detail_url = None

    lines = [
        "<h2>Item Description</h2>",
        f"<p><strong>{title}</strong></p>",
    ]
    if brand:
        lines.append(f"<p><strong>Brand:</strong> {brand}</p>")
    if category:
        lines.append(f"<p><strong>Category:</strong> {category}</p>")

    lines.append(f"<p><strong>Price:</strong> ${listing_price:.2f}</p>")

    if detail_url:
        lines.append(
            f'<p><a href="{detail_url}" target="_blank">'
            "View on Amazon</a></p>"
        )

    lines.append("<p>Condition: New</p>")
    lines.append("<p>Shipping: Fast and free shipping from US warehouse.</p>")

    return "\n".join(lines)


async def create_listing_from_product(
    db: AsyncSession,
    product_id: int,
    pricing_rule_id: Optional[int] = None,
) -> Listing:
    """Orchestrate the full listing-creation flow for a product.

    1. Load the Product by ID.
    2. Calculate listing price via the pricing service.
    3. Generate eBay-optimized title and description.
    4. Create a ``Listing`` record in ``draft`` status.
    5. Return the created listing.
    """
    product = await get_product(db, product_id)
    if not product:
        raise ValueError(f"Product {product_id} not found")

    # Calculate price
    listing_price = await pricing_service.calculate_listing_price(
        db, product, rule_id=pricing_rule_id
    )
    if listing_price is None:
        raise ValueError(
            f"Could not calculate listing price for product {product_id}"
        )

    title = generate_listing_title(product)
    description = generate_listing_description(product, listing_price)

    listing = Listing(
        product_id=product.id,
        title=title,
        listing_price=listing_price,
        quantity=1,
        status=ListingStatus.draft,
        # eBay category is left empty here; caller or a future enrichment step
        # can populate it.
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    logger.info(
        "Created draft listing %s for product %s (price=%s)",
        listing.id,
        product_id,
        listing_price,
    )
    return listing


async def publish_listing(
    db: AsyncSession,
    listing_id: int,
) -> Listing:
    """Publish a draft listing to eBay.

    1. Call ``EbayAPI.create_listing()`` with formatted data.
    2. Update the ``Listing`` status to ``active`` and set
       ``ebay_item_id``, ``ebay_sku``, ``started_at``.
    3. Log the publish action.
    """
    from app.services.listing_service import get_listing

    listing = await get_listing(db, listing_id)
    if not listing:
        raise ValueError(f"Listing {listing_id} not found")
    if listing.status != ListingStatus.draft:
        raise ValueError(
            f"Listing {listing_id} must be in draft status to publish (current: {listing.status.value})"
        )

    product = await get_product(db, listing.product_id)
    if not product:
        raise ValueError(f"Product for listing {listing_id} not found")

    # Re-calculate price at publish time so the latest rules are applied.
    price = await pricing_service.calculate_listing_price(db, product)
    if price is not None:
        listing.listing_price = price

    sku = listing.ebay_sku or f"LISTING-{listing.id}"
    listing_data = {
        "sku": sku,
        "title": listing.title,
        "description": generate_listing_description(product, listing.listing_price),
        "brand": product.brand,
        "image_urls": [product.image_url] if product.image_url else [],
        "condition": "NEW",
        "quantity": listing.quantity,
        "price": str(listing.listing_price),
        "currency": "USD",
        "category_id": listing.ebay_category_id or "",
        "listing_duration": listing.listing_duration or "GTC",
    }

    api = EbayAPI()
    try:
        result = await api.create_listing(listing_data)
    finally:
        await api.close()

    listing.status = ListingStatus.active
    listing.ebay_item_id = result.get("item_id")
    listing.ebay_sku = sku
    listing.started_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(listing)

    logger.info(
        "Published listing %s to eBay (item_id=%s, sku=%s)",
        listing.id,
        listing.ebay_item_id,
        listing.ebay_sku,
    )
    return listing


async def create_and_publish_listing(
    db: AsyncSession,
    product_id: int,
    pricing_rule_id: Optional[int] = None,
) -> Listing:
    """Convenience wrapper that creates a draft listing and immediately publishes it."""
    listing = await create_listing_from_product(db, product_id, pricing_rule_id)
    return await publish_listing(db, listing.id)
