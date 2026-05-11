import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
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

_amazon_circuit_breaker = CircuitBreaker(
    name="amazon_api",
    config=CircuitBreakerConfig(
        failure_threshold=settings.CB_FAILURE_THRESHOLD,
        recovery_timeout=settings.CB_RECOVERY_TIMEOUT_SECONDS,
        half_open_max_calls=settings.CB_HALF_OPEN_MAX_CALLS,
    ),
)

_amazon_retry_config = RetryConfig(
    max_retries=settings.RETRY_MAX_RETRIES,
    base_delay=settings.RETRY_BASE_DELAY_SECONDS,
    max_delay=settings.RETRY_MAX_DELAY_SECONDS,
    exponential_base=settings.RETRY_EXPONENTIAL_BASE,
)


class AmazonAPIError(Exception):
    """Raised when the Amazon Product Advertising API returns an error or the request fails."""

    pass


def _sha256_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    k_signing = _hmac_sha256(k_service, "aws4_request")
    return k_signing


def _sign_request(
    method: str,
    path: str,
    headers: Dict[str, str],
    payload: str,
    access_key: str,
    secret_key: str,
    region: str,
) -> str:
    """Generate the AWS SigV4 Authorization header for Product Advertising API."""
    algorithm = "AWS4-HMAC-SHA256"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    headers = {k.lower(): v for k, v in headers.items()}
    headers["x-amz-date"] = amz_date

    sorted_headers = dict(sorted(headers.items()))

    canonical_headers = ""
    signed_headers = ""
    for key, value in sorted_headers.items():
        canonical_headers += f"{key}:{value}\n"
        signed_headers += f"{key};"
    signed_headers = signed_headers.rstrip(";")

    payload_hash = _sha256_hash(payload)

    canonical_request = (
        f"{method}\n"
        f"{path}\n"
        f"\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    credential_scope = f"{date_stamp}/{region}/ProductAdvertisingAPI/aws4_request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{_sha256_hash(canonical_request)}"
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, "ProductAdvertisingAPI")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return auth_header, amz_date


class AmazonProductAPI:
    """Client for the Amazon Product Advertising API v5.

    Handles AWS SigV4 authentication, request construction, and response parsing.
    """

    def __init__(self):
        self.access_key = settings.AMAZON_ACCESS_KEY
        self.secret_key = settings.AMAZON_SECRET_KEY
        self.partner_tag = settings.AMAZON_PARTNER_TAG
        self.host = settings.AMAZON_HOST
        self.region = settings.AMAZON_REGION
        self._client = httpx.AsyncClient(timeout=30.0)
        self._default_resources = [
            "Images.Primary.Large",
            "ItemInfo.Title",
            "ItemInfo.Brand",
            "Offers.Listings.Price",
            "BrowseNodeInfo.BrowseNodes",
        ]

    def _check_credentials(self) -> None:
        if not self.access_key or not self.secret_key or not self.partner_tag:
            raise AmazonAPIError("Amazon API credentials are not configured")

    def _build_headers(self, target: str) -> Dict[str, str]:
        return {
            "host": self.host,
            "content-type": "application/json; charset=UTF-8",
            "x-amz-target": target,
            "content-encoding": "amz-1.0",
        }

    async def _raw_post(
        self, path: str, target: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make the raw HTTP POST to Amazon PA-API without retry/circuit logic."""
        self._check_credentials()
        body = json.dumps(payload, separators=(",", ":"))
        headers = self._build_headers(target)
        auth_header, amz_date = _sign_request(
            method="POST",
            path=path,
            headers=headers,
            payload=body,
            access_key=self.access_key,
            secret_key=self.secret_key,
            region=self.region,
        )
        headers["Authorization"] = auth_header
        headers["x-amz-date"] = amz_date

        url = f"https://{self.host}{path}"
        try:
            response = await self._client.post(url, headers=headers, content=body)
        except httpx.RequestError as exc:
            logger.error("Amazon API request failed: %s", exc)
            raise AmazonAPIError(f"Amazon API request failed: {exc}") from exc

        try:
            data = response.json()
        except Exception as exc:
            logger.error("Amazon API invalid JSON response: %s", exc)
            raise AmazonAPIError(f"Amazon API invalid JSON response: {exc}") from exc

        if response.status_code != 200:
            errors = data.get("Errors", [])
            msg = "; ".join(f"{e.get('Code')}: {e.get('Message')}" for e in errors)
            logger.error("Amazon API error %s: %s", response.status_code, msg)
            raise AmazonAPIError(
                f"Amazon API error {response.status_code}: {msg or data}"
            )

        return data

    async def _post(self, path: str, target: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a resilient POST to Amazon PA-API with retry and circuit breaker."""

        def _get_status_code(exc: Exception) -> Optional[int]:
            if isinstance(exc, AmazonAPIError):
                msg = str(exc)
                # Parse "Amazon API error {code}: ..."
                prefix = "Amazon API error "
                if msg.startswith(prefix):
                    rest = msg[len(prefix) :]
                    code_str = rest.split(":", 1)[0].split()[0]
                    try:
                        return int(code_str)
                    except ValueError:
                        pass
            return None

        return await with_retry(
            self._raw_post,
            path,
            target,
            payload,
            config=_amazon_retry_config,
            circuit_breaker=_amazon_circuit_breaker,
            get_status_code=_get_status_code,
        )

    def _extract_item_info(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        asin = item.get("ASIN")
        if not asin:
            return None

        item_info = item.get("ItemInfo") or {}
        title = (item_info.get("Title") or {}).get("DisplayValue")
        brand = (item_info.get("ByLineInfo") or {}).get("Brand") or {}
        brand = brand.get("DisplayValue") if isinstance(brand, dict) else None

        browse_node_info = item.get("BrowseNodeInfo") or {}
        browse_nodes = browse_node_info.get("BrowseNodes", []) if isinstance(browse_node_info, dict) else []
        category = None
        if browse_nodes and isinstance(browse_nodes[0], dict):
            category = browse_nodes[0].get("DisplayName")

        images = item.get("Images") or {}
        primary = (images.get("Primary") or {}) if isinstance(images, dict) else {}
        large = (primary.get("Large") or {}) if isinstance(primary, dict) else {}
        image_url = large.get("URL") if isinstance(large, dict) else None
        detail_page_url = item.get("DetailPageURL")

        offers = item.get("Offers") or {}
        listings = offers.get("Listings", []) if isinstance(offers, dict) else []
        price = None
        currency = None
        if listings and isinstance(listings[0], dict):
            price_info = listings[0].get("Price") or {}
            if isinstance(price_info, dict):
                amount = price_info.get("Amount")
                if amount is not None:
                    price = Decimal(str(amount))
                currency = price_info.get("Currency", "USD")

        return {
            "asin": asin,
            "title": title or "",
            "brand": brand,
            "category": category,
            "image_url": image_url,
            "detail_page_url": detail_page_url,
            "price": price,
            "currency": currency,
        }

    async def search_items(
        self,
        keywords: Optional[str] = None,
        browse_node_id: Optional[str] = None,
        item_count: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search Amazon products by keywords or browse node."""
        logger.info("Amazon search_items: keywords=%s, browse_node=%s", keywords, browse_node_id)
        if not keywords and not browse_node_id:
            raise AmazonAPIError("Either keywords or browse_node_id must be provided for search_items")

        capped_count = max(1, min(item_count, 10))
        if item_count > 10:
            logger.warning("Amazon PA-API SearchItems max ItemCount is 10; capping from %s to 10", item_count)
        payload: Dict[str, Any] = {
            "PartnerTag": self.partner_tag,
            "PartnerType": "Associates",
            "ItemCount": capped_count,
            "Resources": self._default_resources,
        }
        if keywords:
            payload["Keywords"] = keywords
        if browse_node_id:
            payload["BrowseNodeId"] = browse_node_id

        data = await self._post(
            "/paapi5/searchitems",
            "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
            payload,
        )

        results = []
        for item in data.get("SearchResult", {}).get("Items", []):
            info = self._extract_item_info(item)
            if info:
                results.append(info)
        return results

    async def get_items(self, item_ids: List[str]) -> List[Dict[str, Any]]:
        """Look up specific Amazon items by ASIN."""
        logger.info("Amazon get_items: item_ids=%s", item_ids)
        if not item_ids:
            return []

        payload: Dict[str, Any] = {
            "ItemIds": item_ids[:10],
            "ItemIdType": "ASIN",
            "PartnerTag": self.partner_tag,
            "PartnerType": "Associates",
            "Resources": self._default_resources,
        }

        data = await self._post(
            "/paapi5/getitems",
            "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems",
            payload,
        )

        results = []
        for item in data.get("ItemsResult", {}).get("Items", []):
            info = self._extract_item_info(item)
            if info:
                results.append(info)
        return results

    async def get_browse_nodes(self, browse_node_ids: List[str]) -> List[Dict[str, Any]]:
        """Retrieve Amazon category browse nodes."""
        logger.info("Amazon get_browse_nodes: ids=%s", browse_node_ids)
        if not browse_node_ids:
            return []

        payload: Dict[str, Any] = {
            "BrowseNodeIds": browse_node_ids[:10],
            "PartnerTag": self.partner_tag,
            "PartnerType": "Associates",
            "Resources": [
                "BrowseNodeInfo.BrowseNodes",
                "BrowseNodeInfo.Ancestor",
            ],
        }

        data = await self._post(
            "/paapi5/getbrowsenodes",
            "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetBrowseNodes",
            payload,
        )

        results = []
        for node in data.get("BrowseNodesResult", {}).get("BrowseNodes", []):
            node_id = node.get("Id")
            if not node_id:
                continue
            info = node.get("DisplayName") or node.get("ContextFreeName")
            ancestor = None
            ancestors = node.get("Ancestor", [])
            if ancestors:
                ancestor = ancestors[0].get("DisplayName") or ancestors[0].get("ContextFreeName")
            results.append({
                "id": node_id,
                "name": info,
                "ancestor": ancestor,
            })
        return results

    async def close(self) -> None:
        await self._client.aclose()


amazon_api = AmazonProductAPI()
