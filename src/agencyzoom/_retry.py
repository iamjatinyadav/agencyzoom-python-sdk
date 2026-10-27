"""Pure retry/backoff decisions, shared by the sync and async transports."""

from __future__ import annotations

import math
import random
import time
from email.utils import parsedate_to_datetime

import httpx

from ._config import RetryConfig

__all__ = ["IDEMPOTENT_METHODS", "compute_backoff", "parse_retry_after", "should_retry_status"]

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


def should_retry_status(config: RetryConfig, method: str, status_code: int) -> bool:
    if status_code not in config.retry_statuses:
        return False
    # The server rejected a rate-limited request without processing it.
    if status_code == 429:
        return True
    return method.upper() in IDEMPOTENT_METHODS


def parse_retry_after(response: httpx.Response | None) -> float | None:
    """Return the ``Retry-After`` delay in seconds, if the server sent a valid one."""
    if response is None:
        return None
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    try:
        return max(0.0, retry_at.timestamp() - time.time())
    except (ValueError, OverflowError, OSError):
        return None


def compute_backoff(
    config: RetryConfig, attempt: int, response: httpx.Response | None = None
) -> float:
    """Seconds to wait before retry number ``attempt`` (0-based).

    Uses the server's ``Retry-After`` when available, otherwise exponential backoff
    with "full jitter" so concurrent clients don't retry in lock-step.
    """
    if config.respect_retry_after:
        retry_after = parse_retry_after(response)
        if retry_after is not None:
            return min(retry_after, config.max_backoff)
    try:
        ceiling = min(config.max_backoff, math.ldexp(config.backoff_factor, attempt))
    except OverflowError:
        ceiling = config.max_backoff
    return random.uniform(ceiling / 2, ceiling)
