import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.sourcing_tasks import _run_sourcing_scan, run_sourcing_scan
from app.schemas.schemas import SourcingResult


def _make_mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_task_session():
    session = _make_mock_session()

    @asynccontextmanager
    async def _ctx():
        yield session

    with patch("app.tasks.sourcing_tasks.task_session", _ctx):
        yield session


@pytest.mark.asyncio
async def test_run_sourcing_scan(mock_task_session):
    result1 = SourcingResult(
        asin="B08N5WRWNW",
        title="Test Product",
        amazon_price=Decimal("19.99"),
        estimated_ebay_price=Decimal("25.99"),
        estimated_margin=0.20,
        category="Electronics",
        image_url="https://example.com/img.jpg",
    )
    with patch(
        "app.tasks.sourcing_tasks.search_and_source",
        new_callable=AsyncMock,
        return_value=[result1],
    ) as mock_search:
        result = await _run_sourcing_scan(
            keywords=["test"], category="123", max_results=10
        )
        assert result["found"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["asin"] == "B08N5WRWNW"
        mock_search.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_sourcing_scan_empty(mock_task_session):
    with patch(
        "app.tasks.sourcing_tasks.search_and_source",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_search:
        result = await _run_sourcing_scan(
            keywords=["test"], category="123", max_results=10
        )
        assert result["found"] == 0
        assert result["results"] == []
        mock_search.assert_awaited_once()


def test_run_sourcing_scan_wrapper():
    with patch(
        "app.tasks.sourcing_tasks._run_sourcing_scan",
        new_callable=AsyncMock,
        return_value={"found": 5},
    ) as mock_sync:
        result = run_sourcing_scan(
            keywords=["test"], category="123", max_results=10
        )
        assert result == {"found": 5}
        mock_sync.assert_awaited_once_with(["test"], "123", 10)


def test_run_sourcing_scan_wrapper_retry():
    with patch.object(
        run_sourcing_scan, "retry", side_effect=Exception("retry called")
    ) as mock_retry:
        with patch(
            "app.tasks.sourcing_tasks.run_async",
            side_effect=Exception("fail"),
        ):
            with pytest.raises(Exception, match="retry called"):
                run_sourcing_scan(keywords=["test"])
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            countdown = kwargs.get("countdown")
            assert countdown is not None
            assert countdown != 60
            assert 0 < countdown <= 60
