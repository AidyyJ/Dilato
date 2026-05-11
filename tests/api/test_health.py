import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_check_all_healthy(client):
    with patch("app.api.v1.endpoints.health.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            response = await client.get("/api/v1/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["checks"]["database"] == "ok"
            assert data["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_check_db_unavailable(client):
    with patch("app.api.v1.endpoints.health.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("connection refused")
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            response = await client.get("/api/v1/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert "unavailable" in data["checks"]["database"]


@pytest.mark.asyncio
async def test_readiness_check_redis_unavailable(client):
    with patch("app.api.v1.endpoints.health.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_result = AsyncMock()
        mock_result.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping.side_effect = Exception("connection refused")
            mock_redis.return_value = mock_redis_instance

            response = await client.get("/api/v1/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert "unavailable" in data["checks"]["redis"]


@pytest.mark.asyncio
async def test_celery_health_check(client):
    with patch("app.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
        mock_inspector = AsyncMock()
        mock_inspector.stats.return_value = {"celery@worker1": {"total": {}}}
        mock_inspector.active.return_value = {"celery@worker1": []}
        mock_inspect.return_value = mock_inspector

        response = await client.get("/api/v1/health/celery")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "celery@worker1" in data["workers"]


@pytest.mark.asyncio
async def test_celery_health_check_no_workers(client):
    with patch("app.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
        mock_inspector = AsyncMock()
        mock_inspector.stats.return_value = None
        mock_inspector.active.return_value = None
        mock_inspect.return_value = mock_inspector

        response = await client.get("/api/v1/health/celery")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_workers"


@pytest.mark.asyncio
async def test_celery_health_check_error(client):
    with patch("app.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
        mock_inspect.side_effect = Exception("broker unreachable")

        response = await client.get("/api/v1/health/celery")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
