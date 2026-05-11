import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.utils import task_session, get_celery_retry_countdown


@pytest.mark.asyncio
async def test_task_session_happy_path():
    mock_session = AsyncMock()

    with patch("app.tasks.utils.async_session_factory", return_value=mock_session):
        async with task_session() as session:
            await session.commit()

    mock_session.commit.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_session_close_on_exception():
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock(side_effect=Exception("db error"))

    with patch("app.tasks.utils.async_session_factory", return_value=mock_session):
        with pytest.raises(Exception, match="db error"):
            async with task_session() as session:
                await session.commit()

    mock_session.close.assert_awaited_once()


def test_get_celery_retry_countdown_exponential():
    """get_celery_retry_countdown should return increasing backoff values."""
    task = MagicMock()

    # Countdown should always be in [1, 60]
    for retries in range(4):
        task.request.retries = retries
        countdown = get_celery_retry_countdown(task)
        assert 1 <= countdown <= 60

    # At high attempts the delay is capped at 60s
    task.request.retries = 10
    assert get_celery_retry_countdown(task) <= 60

    # Statistically, higher attempts yield higher average countdowns
    def _avg(retries, n=50):
        total = 0
        for _ in range(n):
            task.request.retries = retries
            total += get_celery_retry_countdown(task)
        return total / n

    avg_0 = _avg(0)
    avg_2 = _avg(2)
    avg_4 = _avg(4)
    assert avg_4 > avg_2 > avg_0
