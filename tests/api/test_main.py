import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest.fixture
async def test_client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_global_exception_handler_returns_structured_error():
    """Unhandled exceptions should return a consistent {detail, status_code} envelope."""
    app = create_app()

    @app.get("/_test_error")
    async def _test_error():
        raise RuntimeError("unexpected boom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/_test_error")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert data["status_code"] == 500
    assert "unexpected boom" in data["detail"]
