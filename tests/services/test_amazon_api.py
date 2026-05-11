import json
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx

from app.services.amazon_api import AmazonProductAPI, AmazonAPIError


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_ACCESS_KEY", "AKIAIOSFODNN7EXAMPLE")
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_SECRET_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_PARTNER_TAG", "mytag-20")
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_HOST", "webservices.amazon.com")
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_REGION", "us-east-1")
    instance = AmazonProductAPI()
    instance._client = AsyncMock()
    return instance


@pytest.mark.asyncio
async def test_search_items_success(api):
    api._client.post.return_value = FakeResponse(200, {
        "SearchResult": {
            "Items": [
                {
                    "ASIN": "B08N5WRWNW",
                    "DetailPageURL": "https://www.amazon.com/dp/B08N5WRWNW",
                    "ItemInfo": {
                        "Title": {"DisplayValue": "Test Product"},
                        "ByLineInfo": {"Brand": {"DisplayValue": "TestBrand"}},
                    },
                    "Images": {
                        "Primary": {"Large": {"URL": "https://example.com/img.jpg"}},
                    },
                    "Offers": {
                        "Listings": [
                            {"Price": {"Amount": 19.99, "Currency": "USD"}},
                        ],
                    },
                    "BrowseNodeInfo": {
                        "BrowseNodes": [{"DisplayName": "Electronics"}],
                    },
                }
            ]
        }
    })

    results = await api.search_items(keywords="test", item_count=5)

    assert len(results) == 1
    assert results[0]["asin"] == "B08N5WRWNW"
    assert results[0]["title"] == "Test Product"
    assert results[0]["brand"] == "TestBrand"
    assert results[0]["category"] == "Electronics"
    assert results[0]["image_url"] == "https://example.com/img.jpg"
    assert results[0]["detail_page_url"] == "https://www.amazon.com/dp/B08N5WRWNW"
    assert results[0]["price"] == Decimal("19.99")
    assert results[0]["currency"] == "USD"

    _, kwargs = api._client.post.call_args
    body = json.loads(kwargs["content"])
    assert body["Keywords"] == "test"
    assert body["PartnerTag"] == "mytag-20"
    assert body["PartnerType"] == "Associates"
    assert body["ItemCount"] == 5
    assert "Authorization" in kwargs["headers"]
    assert kwargs["headers"]["Authorization"].startswith("AWS4-HMAC-SHA256")
    assert "x-amz-date" in kwargs["headers"]


@pytest.mark.asyncio
async def test_search_items_caps_item_count(api):
    api._client.post.return_value = FakeResponse(200, {"SearchResult": {"Items": []}})
    await api.search_items(keywords="test", item_count=20)
    _, kwargs = api._client.post.call_args
    body = json.loads(kwargs["content"])
    assert body["ItemCount"] == 10


@pytest.mark.asyncio
async def test_search_items_missing_params(api):
    with pytest.raises(AmazonAPIError, match="Either keywords or browse_node_id"):
        await api.search_items()


@pytest.mark.asyncio
async def test_search_items_http_error(api):
    api._client.post.return_value = FakeResponse(400, {
        "Errors": [
            {"Code": "InvalidParameterValue", "Message": "Bad request"},
        ]
    })
    with pytest.raises(AmazonAPIError, match="InvalidParameterValue"):
        await api.search_items(keywords="test")


@pytest.mark.asyncio
async def test_search_items_502_error(api):
    api._client.post.return_value = FakeResponse(502, {
        "Errors": [
            {"Code": "ServiceUnavailable", "Message": "Service temporarily unavailable"},
        ]
    })
    with pytest.raises(AmazonAPIError, match="ServiceUnavailable"):
        await api.search_items(keywords="test")


@pytest.mark.asyncio
async def test_get_items_404_error(api):
    api._client.post.return_value = FakeResponse(404, {
        "Errors": [
            {"Code": "NotFound", "Message": "Item not found"},
        ]
    })
    with pytest.raises(AmazonAPIError, match="NotFound"):
        await api.get_items(["B000000000"])


@pytest.mark.asyncio
async def test_search_items_network_error(api):
    api._client.post.side_effect = httpx.ConnectError("Connection failed")
    with pytest.raises(AmazonAPIError, match="Connection failed"):
        await api.search_items(keywords="test")


@pytest.mark.asyncio
async def test_get_items_success(api):
    api._client.post.return_value = FakeResponse(200, {
        "ItemsResult": {
            "Items": [
                {
                    "ASIN": "B08N5M7S6K",
                    "ItemInfo": {
                        "Title": {"DisplayValue": "Widget"},
                    },
                    "Offers": {
                        "Listings": [
                            {"Price": {"Amount": 9.99, "Currency": "USD"}},
                        ],
                    },
                }
            ]
        }
    })

    results = await api.get_items(["B08N5M7S6K"])
    assert len(results) == 1
    assert results[0]["asin"] == "B08N5M7S6K"
    assert results[0]["title"] == "Widget"
    assert results[0]["price"] == Decimal("9.99")

    _, kwargs = api._client.post.call_args
    body = json.loads(kwargs["content"])
    assert body["ItemIds"] == ["B08N5M7S6K"]
    assert body["ItemIdType"] == "ASIN"


@pytest.mark.asyncio
async def test_get_items_empty_list(api):
    results = await api.get_items([])
    assert results == []
    api._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_get_items_truncates_to_ten(api):
    api._client.post.return_value = FakeResponse(200, {"ItemsResult": {"Items": []}})
    await api.get_items([str(i) for i in range(15)])
    _, kwargs = api._client.post.call_args
    body = json.loads(kwargs["content"])
    assert len(body["ItemIds"]) == 10


@pytest.mark.asyncio
async def test_get_browse_nodes_success(api):
    api._client.post.return_value = FakeResponse(200, {
        "BrowseNodesResult": {
            "BrowseNodes": [
                {
                    "Id": "123",
                    "DisplayName": "Gadgets",
                    "Ancestor": [
                        {"DisplayName": "Electronics"},
                    ],
                }
            ]
        }
    })

    results = await api.get_browse_nodes(["123"])
    assert len(results) == 1
    assert results[0]["id"] == "123"
    assert results[0]["name"] == "Gadgets"
    assert results[0]["ancestor"] == "Electronics"

    _, kwargs = api._client.post.call_args
    body = json.loads(kwargs["content"])
    assert body["BrowseNodeIds"] == ["123"]


@pytest.mark.asyncio
async def test_get_browse_nodes_empty_list(api):
    results = await api.get_browse_nodes([])
    assert results == []
    api._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_missing_credentials(monkeypatch):
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_ACCESS_KEY", "")
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_SECRET_KEY", "")
    monkeypatch.setattr("app.services.amazon_api.settings.AMAZON_PARTNER_TAG", "")
    bad_api = AmazonProductAPI()
    bad_api._client = AsyncMock()
    with pytest.raises(AmazonAPIError, match="credentials are not configured"):
        await bad_api.search_items(keywords="test")


@pytest.mark.asyncio
async def test_close(api):
    api._client.aclose = AsyncMock()
    await api.close()
    api._client.aclose.assert_awaited_once()
