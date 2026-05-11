import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import get_current_active_user, get_password_hash
from app.models.models import User
from app.core.database import get_db


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def clear_auth_override():
    app.dependency_overrides.pop(get_current_active_user, None)
    yield


@pytest.fixture
def mock_user():
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_superuser=False,
    )
    user.hashed_password = get_password_hash("secret123")
    return user


@pytest.fixture
def mock_db_session(mock_user):
    session = AsyncMock()
    result = AsyncMock()
    result.scalar_one_or_none.return_value = mock_user
    session.execute.return_value = result
    return session


@pytest.fixture(autouse=True)
def override_db(mock_db_session):
    async def _get_db():
        yield mock_db_session
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# POST /api/v1/auth/register
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_success(client):
    session = AsyncMock()
    result = AsyncMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    async def _get_db():
        yield session
    app.dependency_overrides[get_db] = _get_db

    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "newuser", "email": "new@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate(client, mock_user):
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_success(client, mock_user):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "secret123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, mock_user):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Protected endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client):
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_active_user, None)
    response = await client.get("/api/v1/products/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token(client):
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_active_user, None)
    response = await client.get(
        "/api/v1/products/",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert response.status_code == 401
