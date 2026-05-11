import base64
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    RetryConfig,
    with_retry,
)

logger = logging.getLogger(__name__)

_ebay_circuit_breaker = CircuitBreaker(
    name="ebay_api",
    config=CircuitBreakerConfig(
        failure_threshold=settings.CB_FAILURE_THRESHOLD,
        recovery_timeout=settings.CB_RECOVERY_TIMEOUT_SECONDS,
        half_open_max_calls=settings.CB_HALF_OPEN_MAX_CALLS,
    ),
)

_ebay_retry_config = RetryConfig(
    max_retries=settings.RETRY_MAX_RETRIES,
    base_delay=settings.RETRY_BASE_DELAY_SECONDS,
    max_delay=settings.RETRY_MAX_DELAY_SECONDS,
    exponential_base=settings.RETRY_EXPONENTIAL_BASE,
)


class EbayAPIError(Exception):
    """Raised when the eBay REST API returns an error or the request fails."""

    pass


class EbayAPI:
    """Client for the eBay REST API.

    Handles OAuth token management, listing CRUD, and order retrieval.
    """

    def __init__(self):
        self.client_id = settings.EBAY_CLIENT_ID
        self.client_secret = settings.EBAY_CLIENT_SECRET
        self.dev_id = settings.EBAY_DEV_ID
        self.ru_name = settings.EBAY_RU_NAME
        self.site_id = settings.EBAY_SITE_ID
        self.base_url = settings.EBAY_API_BASE_URL
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self._marketplace_id = self._resolve_marketplace_id()

    def _resolve_marketplace_id(self) -> str:
        mapping = {
            0: "EBAY_US",
            3: "EBAY_GB",
            15: "EBAY_AU",
            2: "EBAY_CA",
            77: "EBAY_DE",
            101: "EBAY_IT",
            71: "EBAY_FR",
            186: "EBAY_ES",
        }
        return mapping.get(self.site_id, "EBAY_US")

    def _check_credentials(self) -> None:
        if not self.client_id or not self.client_secret:
            raise EbayAPIError("eBay API credentials are not configured")

    async def _raw_refresh_token(self) -> str:
        """Obtain a new OAuth access token using the client credentials flow."""
        self._check_credentials()
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": (
                "https://api.ebay.com/oauth/api_scope "
                "https://api.ebay.com/oauth/api_scope/sell.inventory "
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment"
            ),
        }
        try:
            response = await self._client.post(
                f"{self.base_url}/identity/v1/oauth2/token",
                headers=headers,
                data=data,
            )
        except httpx.RequestError as exc:
            logger.error("eBay OAuth request failed: %s", exc)
            raise EbayAPIError(f"eBay OAuth request failed: {exc}") from exc

        try:
            payload = response.json()
        except Exception as exc:
            logger.error("eBay OAuth invalid JSON response: %s", exc)
            raise EbayAPIError(f"eBay OAuth invalid JSON response: {exc}") from exc

        if response.status_code != 200:
            error_msg = (
                payload.get("error_description")
                or payload.get("error")
                or str(payload)
            )
            logger.error("eBay OAuth error %s: %s", response.status_code, error_msg)
            raise EbayAPIError(
                f"eBay OAuth error {response.status_code}: {error_msg}"
            )

        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 7200)
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in - 300
        )
        logger.info("eBay OAuth token refreshed, expires in %s seconds", expires_in)
        return self._access_token

    async def _refresh_token(self) -> str:
        """Refresh token with circuit breaker and retry."""

        def _get_status_code(exc: Exception) -> Optional[int]:
            if isinstance(exc, EbayAPIError):
                msg = str(exc)
                prefix = "eBay OAuth error "
                if msg.startswith(prefix):
                    rest = msg[len(prefix) :]
                    code_str = rest.split(":", 1)[0].split()[0]
                    try:
                        return int(code_str)
                    except ValueError:
                        pass
            return None

        return await with_retry(
            self._raw_refresh_token,
            config=_ebay_retry_config,
            circuit_breaker=_ebay_circuit_breaker,
            get_status_code=_get_status_code,
        )

    async def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        now = datetime.now(timezone.utc)
        if (
            self._access_token
            and self._token_expires_at
            and now < self._token_expires_at
        ):
            return self._access_token
        return await self._refresh_token()

    async def _raw_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the eBay REST API without resilience logic."""
        token = await self._ensure_token()
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": self._marketplace_id,
        }
        if headers:
            request_headers.update(headers)

        url = f"{self.base_url}{path}"
        try:
            response = await self._client.request(
                method=method,
                url=url,
                headers=request_headers,
                json=json_data,
                params=params,
            )
        except httpx.RequestError as exc:
            logger.error("eBay API request failed: %s %s - %s", method, path, exc)
            raise EbayAPIError(f"eBay API request failed: {exc}") from exc

        if response.status_code == 204:
            return {}

        try:
            data = response.json()
        except Exception as exc:
            logger.error("eBay API invalid JSON response: %s", exc)
            raise EbayAPIError(f"eBay API invalid JSON response: {exc}") from exc

        if response.status_code >= 400:
            errors = data.get("errors", [])
            if errors:
                msgs = "; ".join(
                    f"{e.get('errorId')}: {e.get('message')}" for e in errors
                )
            else:
                msgs = data.get("message", str(data))
            logger.error(
                "eBay API error %s %s: %s", response.status_code, path, msgs
            )
            raise EbayAPIError(f"eBay API error {response.status_code}: {msgs}")

        return data

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a resilient authenticated request to the eBay REST API.

        Handles 401 by refreshing the token and retrying once immediately.
        Other retryable errors go through exponential backoff.
        """

        def _get_status_code(exc: Exception) -> Optional[int]:
            if isinstance(exc, EbayAPIError):
                msg = str(exc)
                prefix = "eBay API error "
                if msg.startswith(prefix):
                    rest = msg[len(prefix) :]
                    code_str = rest.split(":", 1)[0].split()[0]
                    try:
                        return int(code_str)
                    except ValueError:
                        pass
            return None

        async def _do_request() -> Dict[str, Any]:
            try:
                return await self._raw_request(
                    method, path, json_data=json_data, params=params, headers=headers
                )
            except EbayAPIError as exc:
                status_code = _get_status_code(exc)
                if status_code == 401:
                    logger.warning(
                        "eBay API returned 401 for %s %s, refreshing token and retrying",
                        method,
                        path,
                    )
                    # Force token refresh
                    self._access_token = None
                    self._token_expires_at = None
                    # Retry once with fresh token
                    return await self._raw_request(
                        method, path, json_data=json_data, params=params, headers=headers
                    )
                raise

        return await with_retry(
            _do_request,
            config=_ebay_retry_config,
            circuit_breaker=_ebay_circuit_breaker,
            get_status_code=_get_status_code,
        )

    # ------------------------------------------------------------------
    # Inventory Item APIs
    # ------------------------------------------------------------------

    async def create_or_update_inventory_item(
        self, sku: str, item_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create or replace an inventory item for the given SKU."""
        logger.info("eBay create_or_update_inventory_item: sku=%s", sku)
        return await self._request(
            "PUT",
            f"/sell/inventory/v1/inventory_item/{sku}",
            json_data=item_data,
            headers={"Content-Language": "en-US"},
        )

    async def get_inventory_item(self, sku: str) -> Optional[Dict[str, Any]]:
        """Retrieve an inventory item by SKU."""
        logger.info("eBay get_inventory_item: sku=%s", sku)
        try:
            return await self._request(
                "GET", f"/sell/inventory/v1/inventory_item/{sku}"
            )
        except EbayAPIError as exc:
            err_msg = str(exc).lower()
            if "not found" in err_msg or "does not exist" in err_msg:
                return None
            raise

    async def delete_inventory_item(self, sku: str) -> None:
        """Delete an inventory item by SKU."""
        logger.info("eBay delete_inventory_item: sku=%s", sku)
        await self._request("DELETE", f"/sell/inventory/v1/inventory_item/{sku}")

    # ------------------------------------------------------------------
    # Offer APIs
    # ------------------------------------------------------------------

    async def create_offer(self, offer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new offer for an inventory item."""
        logger.info("eBay create_offer: sku=%s", offer_data.get("sku"))
        return await self._request(
            "POST", "/sell/inventory/v1/offer", json_data=offer_data
        )

    async def get_offer(self, offer_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an offer by its ID."""
        logger.info("eBay get_offer: offer_id=%s", offer_id)
        try:
            return await self._request(
                "GET", f"/sell/inventory/v1/offer/{offer_id}"
            )
        except EbayAPIError as exc:
            err_msg = str(exc).lower()
            if "not found" in err_msg or "does not exist" in err_msg:
                return None
            raise

    async def get_offers(
        self, limit: int = 200, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve seller offers with pagination."""
        data = await self._request(
            "GET",
            "/sell/inventory/v1/offer",
            params={"limit": limit, "offset": offset},
        )
        return data.get("offers", [])

    async def _find_offer_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Find the first active offer matching the SKU.

        eBay's GET /sell/inventory/v1/offer does not support SKU filtering,
        so we paginate client-side. Typical reseller volumes make this acceptable.
        """
        offset = 0
        page_size = 200
        while True:
            offers = await self.get_offers(limit=page_size, offset=offset)
            for offer in offers:
                if offer.get("sku") == sku:
                    return offer
            if len(offers) < page_size:
                break
            offset += page_size
        return None

    async def update_offer(
        self, offer_id: str, offer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing offer."""
        logger.info("eBay update_offer: offer_id=%s", offer_id)
        return await self._request(
            "PUT", f"/sell/inventory/v1/offer/{offer_id}", json_data=offer_data
        )

    async def publish_offer(self, offer_id: str) -> Dict[str, Any]:
        """Publish an offer to create a live eBay listing."""
        logger.info("eBay publish_offer: offer_id=%s", offer_id)
        return await self._request(
            "POST", f"/sell/inventory/v1/offer/{offer_id}/publish"
        )

    async def withdraw_offer(self, offer_id: str) -> Dict[str, Any]:
        """Withdraw a published offer to end the listing."""
        logger.info("eBay withdraw_offer: offer_id=%s", offer_id)
        return await self._request(
            "POST", f"/sell/inventory/v1/offer/{offer_id}/withdraw"
        )

    # ------------------------------------------------------------------
    # High-level Listing CRUD
    # ------------------------------------------------------------------

    async def create_listing(self, listing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a listing on eBay via the Inventory API.

        Expected keys in *listing_data*:
        - sku (str): required
        - title (str): required
        - description (str): required
        - brand (str): optional
        - image_urls (List[str]): optional
        - condition (str): default "NEW"
        - quantity (int): default 1
        - price (str): required
        - currency (str): default "USD"
        - category_id (str): required for offer
        - listing_duration (str): default "GTC"
        """
        logger.info("eBay create_listing: sku=%s", listing_data.get("sku"))
        sku = listing_data.get("sku")
        if not sku:
            raise EbayAPIError("sku is required to create an eBay listing")

        price = listing_data.get("price")
        if price is None:
            raise EbayAPIError("price is required to create an eBay listing")

        try:
            price_val = Decimal(str(price))
        except Exception:
            raise EbayAPIError("price must be a valid number greater than 0")
        if price_val <= 0:
            raise EbayAPIError("price must be greater than 0")

        condition = listing_data.get("condition", "NEW")
        quantity = listing_data.get("quantity", 1)
        currency = listing_data.get("currency", "USD")

        # Build inventory item
        product: Dict[str, Any] = {
            "title": listing_data["title"],
            "description": listing_data["description"],
        }
        if listing_data.get("brand"):
            product["brand"] = listing_data["brand"]
        if listing_data.get("image_urls"):
            product["imageUrls"] = listing_data["image_urls"]

        inventory_item = {
            "availability": {
                "shipToLocationAvailability": {"quantity": quantity}
            },
            "condition": condition,
            "product": product,
        }
        await self.create_or_update_inventory_item(sku, inventory_item)

        # Build offer
        offer: Dict[str, Any] = {
            "sku": sku,
            "marketplaceId": self._marketplace_id,
            "format": "FIXED_PRICE",
            "availableQuantity": quantity,
            "categoryId": listing_data.get("category_id", ""),
            "listingDescription": listing_data["description"],
            "pricingSummary": {
                "price": {
                    "currency": currency,
                    "value": str(price),
                }
            },
        }
        if listing_data.get("listing_duration"):
            offer["listingDuration"] = listing_data["listing_duration"]

        created_offer = await self.create_offer(offer)
        offer_id = created_offer.get("offerId")
        if not offer_id:
            raise EbayAPIError("eBay createOffer did not return an offerId")

        publish_result = await self.publish_offer(offer_id)
        item_id = publish_result.get("listingId")

        return {
            "sku": sku,
            "offer_id": offer_id,
            "item_id": item_id,
            "status": "active",
        }

    async def get_listing(self, ebay_item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a listing from eBay.

        *ebay_item_id* is treated as the SKU for inventory item lookup.
        """
        logger.info("eBay get_listing: item_id=%s", ebay_item_id)
        item = await self.get_inventory_item(ebay_item_id)
        if not item:
            return None
        return {"sku": ebay_item_id, "inventory_item": item}

    async def update_listing(
        self, ebay_item_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing eBay listing.

        *ebay_item_id* is treated as the SKU. If *updates* contains
        ``offer_id``, the corresponding offer is also updated.
        """
        logger.info("eBay update_listing: item_id=%s", ebay_item_id)
        sku = ebay_item_id

        item = await self.get_inventory_item(sku)
        if not item:
            raise EbayAPIError(
                f"eBay inventory item not found for SKU {sku}"
            )

        if any(
            k in updates
            for k in (
                "title",
                "description",
                "brand",
                "image_urls",
                "condition",
                "quantity",
            )
        ):
            product = item.get("product", {})
            if updates.get("title"):
                product["title"] = updates["title"]
            if updates.get("description"):
                product["description"] = updates["description"]
            if "brand" in updates:
                product["brand"] = updates["brand"]
            if "image_urls" in updates:
                product["imageUrls"] = updates["image_urls"]

            inventory_item = {
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": updates.get(
                            "quantity",
                            item.get("availability", {})
                            .get("shipToLocationAvailability", {})
                            .get("quantity", 1),
                        )
                    }
                },
                "condition": updates.get("condition", item.get("condition", "NEW")),
                "product": product,
            }
            await self.create_or_update_inventory_item(sku, inventory_item)

        offer_id = updates.get("offer_id")
        if not offer_id:
            offer = await self._find_offer_by_sku(sku)
            if offer:
                offer_id = offer.get("offerId")
        if offer_id:
            offer = await self.get_offer(offer_id)
            if not offer:
                raise EbayAPIError(f"eBay offer not found: {offer_id}")

            if updates.get("price") or updates.get("currency") or "quantity" in updates:
                offer["pricingSummary"] = offer.get("pricingSummary", {})
                offer["pricingSummary"]["price"] = offer["pricingSummary"].get(
                    "price", {}
                )
                if updates.get("price"):
                    offer["pricingSummary"]["price"]["value"] = str(
                        updates["price"]
                    )
                if updates.get("currency"):
                    offer["pricingSummary"]["price"]["currency"] = updates[
                        "currency"
                    ]
                offer["availableQuantity"] = updates.get(
                    "quantity", offer.get("availableQuantity", 1)
                )
            if updates.get("description"):
                offer["listingDescription"] = updates["description"]

            await self.update_offer(offer_id, offer)

        return {"sku": sku, "updated": True}

    async def end_listing(self, ebay_item_id: str) -> Dict[str, Any]:
        """End a listing on eBay by withdrawing its offer.

        *ebay_item_id* is treated as the SKU. The offer is looked up by SKU.
        """
        logger.info("eBay end_listing: item_id=%s", ebay_item_id)
        sku = ebay_item_id

        offer = await self._find_offer_by_sku(sku)
        if not offer:
            raise EbayAPIError(f"No active offer found for SKU {sku}")

        offer_id = offer["offerId"]
        await self.withdraw_offer(offer_id)
        return {"sku": sku, "offer_id": offer_id, "status": "ended"}

    # ------------------------------------------------------------------
    # Fulfillment (Order) APIs
    # ------------------------------------------------------------------

    async def get_orders(self, **kwargs) -> List[Dict[str, Any]]:
        """Retrieve orders from eBay.

        Supported kwargs:
        - limit (int): max results, default 50, max 200
        - offset (int): pagination offset, default 0
        - order_ids (List[str]): specific order IDs
        - filter (str): eBay filter string, e.g.
          ``orderfulfillmentstatus:{NOT_STARTED}``
        """
        logger.info("eBay get_orders called with %s", kwargs)
        params: Dict[str, Any] = {}
        if "limit" in kwargs:
            params["limit"] = max(1, min(kwargs["limit"], 200))
        else:
            params["limit"] = 50
        if "offset" in kwargs:
            params["offset"] = max(0, kwargs["offset"])
        if "order_ids" in kwargs:
            params["orderIds"] = ",".join(kwargs["order_ids"])
        if "filter" in kwargs:
            params["filter"] = kwargs["filter"]

        data = await self._request(
            "GET", "/sell/fulfillment/v1/order", params=params
        )
        return data.get("orders", [])

    async def close(self) -> None:
        await self._client.aclose()


ebay_api = EbayAPI()
