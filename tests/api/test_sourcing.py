import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.core.security import get_current_active_user
from app.models.models import User


@pytest.fixture
async def sourcing_client():
    app = create_app()

    mock_user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_superuser=False,
    )
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
async def test_sourcing_search_error_handling(sourcing_client):
    """search_and_source exceptions should return structured 500, not raw ASGI error."""
    with patch(
        "app.api.v1.endpoints.sourcing.search_and_source",
        new_callable=AsyncMock,
        side_effect=RuntimeError("amazon api down"),
    ):
        response = await sourcing_client.post(
            "/api/v1/sourcing/search",
            json={"keywords": ["test"], "max_results": 10},
        )

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "amazon api down" in data["detail"]
