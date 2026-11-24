import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class TransientError(Exception):
    """An error worth retrying: timeout, HTTP 5xx, rate limiting."""


def call_with_retry(
    func: Callable[[], T],
    *,
    attempts: int,
    retry_on: tuple[type[BaseException], ...],
    base_delay: float = 1.0,
    factor: float = 2.0,
    description: str = "operation",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_on as exc:
            if attempt == attempts:
                logger.error("%s failed after %d attempts: %s", description, attempts, exc)
                raise
            delay = base_delay * factor ** (attempt - 1)
            logger.warning("%s failed (attempt %d/%d), retrying in %.1fs", description, attempt, attempts, delay)
            sleep(delay)
    raise AssertionError("unreachable")