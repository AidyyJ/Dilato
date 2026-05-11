import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    CircuitState,
    RetryConfig,
    calculate_backoff,
    is_retryable_error,
    with_retry,
)


# -----------------------------------------------------------------------------
# Circuit Breaker
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_starts_closed():
    cb = CircuitBreaker(name="test", config=CircuitBreakerConfig(failure_threshold=3))
    assert cb.state == CircuitState.CLOSED
    assert await cb.can_execute() is True


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(name="test", config=CircuitBreakerConfig(failure_threshold=2))
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert await cb.can_execute() is False


@pytest.mark.asyncio
async def test_circuit_half_open_after_timeout():
    cb = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    await asyncio.sleep(0.02)
    assert await cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_closes_on_success_in_half_open():
    cb = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    await cb.record_failure()
    await asyncio.sleep(0.02)
    assert await cb.can_execute() is True
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_reopens_on_failure_in_half_open():
    cb = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    await cb.record_failure()
    await asyncio.sleep(0.02)
    assert await cb.can_execute() is True
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_half_open_max_calls():
    cb = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0.01, half_open_max_calls=2
        ),
    )
    await cb.record_failure()
    await asyncio.sleep(0.02)
    assert await cb.can_execute() is True
    assert await cb.can_execute() is True
    assert await cb.can_execute() is False


# -----------------------------------------------------------------------------
# Backoff calculation
# -----------------------------------------------------------------------------

def test_calculate_backoff_no_jitter():
    delay = calculate_backoff(0, base_delay=1.0, max_delay=60.0, jitter=False)
    assert delay == 1.0
    delay = calculate_backoff(1, base_delay=1.0, max_delay=60.0, jitter=False)
    assert delay == 2.0
    delay = calculate_backoff(2, base_delay=1.0, max_delay=60.0, jitter=False)
    assert delay == 4.0


def test_calculate_backoff_respects_max():
    delay = calculate_backoff(10, base_delay=1.0, max_delay=10.0, jitter=False)
    assert delay == 10.0


def test_calculate_backoff_with_jitter():
    delay = calculate_backoff(0, base_delay=1.0, max_delay=60.0, jitter=True)
    assert 0.75 <= delay <= 1.0


# -----------------------------------------------------------------------------
# Retry differentiation
# -----------------------------------------------------------------------------

def test_is_retryable_network_error():
    assert is_retryable_error(httpx.ConnectError("fail")) is True
    assert is_retryable_error(httpx.TimeoutException("timeout")) is True


def test_is_retryable_status_codes():
    assert is_retryable_error(Exception(), status_code=429) is True
    assert is_retryable_error(Exception(), status_code=500) is True
    assert is_retryable_error(Exception(), status_code=502) is True
    assert is_retryable_error(Exception(), status_code=503) is True
    assert is_retryable_error(Exception(), status_code=504) is True


def test_is_not_retryable_4xx():
    assert is_retryable_error(Exception(), status_code=400) is False
    assert is_retryable_error(Exception(), status_code=403) is False
    assert is_retryable_error(Exception(), status_code=404) is False
    assert is_retryable_error(Exception(), status_code=422) is False


def test_is_retryable_5xx_default():
    assert is_retryable_error(Exception(), status_code=501) is True
    assert is_retryable_error(Exception(), status_code=599) is True


def test_is_not_retryable_non_http():
    assert is_retryable_error(ValueError("bad")) is False


def _make_exc_with_cause(msg: str, cause: Exception) -> Exception:
    try:
        raise RuntimeError(msg) from cause
    except RuntimeError as exc:
        return exc


def test_is_retryable_wrapped_network_error():
    """Wrapped httpx.RequestError should be detected via __cause__."""
    inner = httpx.ConnectError("fail")
    outer = _make_exc_with_cause("outer", inner)
    assert is_retryable_error(outer) is True


def test_is_retryable_deeply_nested_cause():
    inner = httpx.TimeoutException("timeout")
    mid = _make_exc_with_cause("mid", inner)
    outer = _make_exc_with_cause("outer", mid)
    assert is_retryable_error(outer) is True


# -----------------------------------------------------------------------------
# with_retry
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_with_retry_success():
    mock_func = AsyncMock(return_value="ok")
    result = await with_retry(mock_func, config=RetryConfig(max_retries=2))
    assert result == "ok"
    assert mock_func.await_count == 1


@pytest.mark.asyncio
async def test_with_retry_eventual_success():
    mock_func = AsyncMock(side_effect=[httpx.ConnectError("fail"), "ok"])
    with patch("app.core.resilience.asyncio.sleep", new_callable=AsyncMock):
        result = await with_retry(mock_func, config=RetryConfig(max_retries=2))
    assert result == "ok"
    assert mock_func.await_count == 2


@pytest.mark.asyncio
async def test_with_retry_exhausted():
    mock_func = AsyncMock(side_effect=httpx.ConnectError("fail"))
    with patch("app.core.resilience.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.ConnectError):
            await with_retry(mock_func, config=RetryConfig(max_retries=2))
    assert mock_func.await_count == 3


@pytest.mark.asyncio
async def test_with_retry_non_retryable_raises_immediately():
    mock_func = AsyncMock(side_effect=ValueError("bad"))
    with pytest.raises(ValueError, match="bad"):
        await with_retry(mock_func, config=RetryConfig(max_retries=2))
    assert mock_func.await_count == 1


@pytest.mark.asyncio
async def test_with_retry_status_code_non_retryable():
    exc = Exception("err")
    mock_func = AsyncMock(side_effect=exc)
    config = RetryConfig(max_retries=2)
    with pytest.raises(Exception, match="err"):
        await with_retry(
            mock_func,
            config=config,
            get_status_code=lambda e: 400,
        )
    assert mock_func.await_count == 1


@pytest.mark.asyncio
async def test_with_retry_status_code_retryable():
    exc = Exception("err")
    mock_func = AsyncMock(side_effect=exc)
    config = RetryConfig(max_retries=2)
    with patch("app.core.resilience.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(Exception, match="err"):
            await with_retry(
                mock_func,
                config=config,
                get_status_code=lambda e: 502,
            )
    assert mock_func.await_count == 3


@pytest.mark.asyncio
async def test_with_retry_circuit_breaker_open():
    cb = CircuitBreaker(
        name="test", config=CircuitBreakerConfig(failure_threshold=1)
    )
    await cb.record_failure()
    mock_func = AsyncMock()
    with pytest.raises(CircuitBreakerOpen):
        await with_retry(mock_func, circuit_breaker=cb)
    mock_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_with_retry_circuit_breaker_records_failure():
    cb = CircuitBreaker(
        name="test", config=CircuitBreakerConfig(failure_threshold=2)
    )
    mock_func = AsyncMock(side_effect=httpx.ConnectError("fail"))
    config = RetryConfig(max_retries=1)
    with patch("app.core.resilience.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.ConnectError):
            await with_retry(mock_func, config=config, circuit_breaker=cb)
    assert cb._failures == 1


@pytest.mark.asyncio
async def test_with_retry_circuit_breaker_records_success():
    cb = CircuitBreaker(
        name="test", config=CircuitBreakerConfig(failure_threshold=2)
    )
    mock_func = AsyncMock(return_value="ok")
    await with_retry(mock_func, circuit_breaker=cb)
    assert cb._failures == 0
    assert cb.state == CircuitState.CLOSED
