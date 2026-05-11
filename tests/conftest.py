import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/reseller")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://postgres:postgres@db:5432/reseller")

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import get_current_active_user
from app.models.models import User
from app.core.resilience import CircuitState
from app.services.amazon_api import _amazon_circuit_breaker
from app.services.ebay_api import _ebay_circuit_breaker


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset circuit breaker state between tests to avoid cross-test pollution."""
    for cb in (_amazon_circuit_breaker, _ebay_circuit_breaker):
        cb._state = CircuitState.CLOSED
        cb._failures = 0
        cb._last_failure_time = None
        cb._half_open_calls = 0
    yield


@pytest.fixture
def mock_user():
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_superuser=False,
    )


@pytest.fixture
def override_auth(mock_user):
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    yield
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
