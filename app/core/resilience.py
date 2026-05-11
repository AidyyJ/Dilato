import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Set, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and rejecting requests."""

    pass


class NonRetryableError(Exception):
    """Wrapper to indicate an error should not be retried."""

    pass


@dataclass
class RetryConfig:
    """Configuration for retry behavior with exponential backoff."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_statuses: Set[int] = field(
        default_factory=lambda: {429, 500, 502, 503, 504}
    )
    # 401 is handled specially in eBay (token refresh), not globally retryable
    non_retryable_statuses: Set[int] = field(
        default_factory=lambda: {400, 403, 404, 405, 406, 409, 410, 422}
    )


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3


class CircuitBreaker:
    """Async-safe circuit breaker for protecting external API calls.

    Tracks failures in-memory. For distributed deployments, a Redis-backed
    implementation can be swapped in later.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def can_execute(self) -> bool:
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(
                        "Circuit breaker '%s' entering HALF_OPEN state", self.name
                    )
                    # Fall through to HALF_OPEN logic
                else:
                    logger.warning(
                        "Circuit breaker '%s' is OPEN, rejecting request", self.name
                    )
                    return False
            # HALF_OPEN
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1
                if self._half_open_calls <= 0:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
                    self._last_failure_time = None
                    logger.info(
                        "Circuit breaker '%s' closed after recovery", self.name
                    )
            else:
                self._failures = max(0, self._failures - 1)

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            self._last_failure_time = asyncio.get_event_loop().time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' re-opened due to failure in HALF_OPEN",
                    self.name,
                )
            elif self._failures >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' opened after %s failures",
                    self.name,
                    self._failures,
                )

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        elapsed = asyncio.get_event_loop().time() - self._last_failure_time
        return elapsed >= self.config.recovery_timeout


def is_retryable_error(
    exc: Exception,
    status_code: Optional[int] = None,
    retryable_statuses: Optional[Set[int]] = None,
    non_retryable_statuses: Optional[Set[int]] = None,
) -> bool:
    """Determine whether an exception should trigger a retry.

    Rules:
    - Network errors (httpx.RequestError) -> retryable
    - Timeout errors (httpx.TimeoutException) -> retryable
    - Status codes in retryable_statuses -> retryable
    - Status codes in non_retryable_statuses -> not retryable
    - Non-HTTP errors that aren't wrapped -> not retryable
    """
    if retryable_statuses is None:
        retryable_statuses = {429, 500, 502, 503, 504}
    if non_retryable_statuses is None:
        non_retryable_statuses = {400, 403, 404, 405, 406, 409, 410, 422}

    # Unwrap NonRetryableError
    if isinstance(exc, NonRetryableError):
        return False

    # Network-level errors are retryable (including wrapped ones)
    if isinstance(exc, httpx.RequestError):
        return True
    cause = exc.__cause__
    while cause is not None:
        if isinstance(cause, httpx.RequestError):
            return True
        cause = getattr(cause, "__cause__", None)

    if status_code is not None:
        if status_code in retryable_statuses:
            return True
        if status_code in non_retryable_statuses:
            return False
        # Default: 5xx retryable, 4xx not retryable
        if status_code >= 500:
            return True
        if status_code >= 400:
            return False

    return False


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> float:
    """Calculate delay for the given retry attempt using exponential backoff.

    attempt is 0-indexed (0 = first retry).
    """
    delay = base_delay * (exponential_base ** attempt)
    delay = min(delay, max_delay)
    if jitter:
        # Add up to 25% random jitter to avoid thundering herd
        delay = delay * (0.75 + random.random() * 0.25)
    return delay


async def with_retry(
    func: Callable[..., Any],
    *args: Any,
    config: Optional[RetryConfig] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    get_status_code: Optional[Callable[[Exception], Optional[int]]] = None,
    **kwargs: Any,
) -> Any:
    """Execute an async function with circuit breaker and exponential backoff retry.

    Args:
        func: The async callable to wrap.
        *args, **kwargs: Arguments to pass to func.
        config: RetryConfig instance. Uses defaults if None.
        circuit_breaker: Optional CircuitBreaker to guard execution.
        get_status_code: Optional callable to extract HTTP status code from exception.

    Returns:
        The result of func.

    Raises:
        The last exception encountered if all retries are exhausted.
        CircuitBreakerOpen if the circuit breaker rejects the call.
    """
    cfg = config or RetryConfig()

    if circuit_breaker is not None:
        if not await circuit_breaker.can_execute():
            raise CircuitBreakerOpen(
                f"Circuit breaker '{circuit_breaker.name}' is open"
            )

    last_exc: Optional[Exception] = None

    for attempt in range(cfg.max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if circuit_breaker is not None:
                await circuit_breaker.record_success()
            return result
        except Exception as exc:
            last_exc = exc
            status_code = None
            if get_status_code is not None:
                try:
                    status_code = get_status_code(exc)
                except Exception:
                    pass

            if not is_retryable_error(
                exc,
                status_code=status_code,
                retryable_statuses=cfg.retryable_statuses,
                non_retryable_statuses=cfg.non_retryable_statuses,
            ):
                if circuit_breaker is not None:
                    await circuit_breaker.record_failure()
                raise

            if attempt < cfg.max_retries:
                delay = calculate_backoff(
                    attempt,
                    base_delay=cfg.base_delay,
                    max_delay=cfg.max_delay,
                    exponential_base=cfg.exponential_base,
                    jitter=cfg.jitter,
                )
                logger.warning(
                    "Retryable error on attempt %s for %s: %s. "
                    "Retrying in %.2f seconds...",
                    attempt + 1,
                    func.__name__,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %s retries exhausted for %s: %s",
                    cfg.max_retries,
                    func.__name__,
                    exc,
                )

    if circuit_breaker is not None and last_exc is not None:
        await circuit_breaker.record_failure()
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unexpected state in with_retry")
