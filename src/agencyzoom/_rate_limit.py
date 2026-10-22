"""Token-bucket arithmetic for client-side rate limiting.

The bucket itself does no sleeping or locking: the sync/async transports wrap it
with the right primitives. Keeping the math here lets both share one tested
implementation.
"""

from __future__ import annotations

import time
from collections.abc import Callable

__all__ = ["TokenBucket"]


class TokenBucket:
    """Allows ``rate_per_minute`` requests per minute with bursts up to ``capacity``."""

    __slots__ = ("_clock", "_last", "_refill_per_second", "_tokens", "capacity")

    def __init__(
        self,
        rate_per_minute: float,
        *,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = capacity if capacity is not None else rate_per_minute
        self._refill_per_second = rate_per_minute / 60.0
        self._tokens = self.capacity
        self._clock = clock
        self._last = clock()

    def reserve(self) -> float:
        """Take one token and return how long the caller must wait before using it.

        Tokens may go negative: each caller reserves its own future slot, so
        concurrent callers are spaced out correctly instead of stampeding together.
        """
        now = self._clock()
        self._tokens = min(
            self.capacity, self._tokens + (now - self._last) * self._refill_per_second
        )
        self._last = now
        self._tokens -= 1.0
        if self._tokens >= 0:
            return 0.0
        return -self._tokens / self._refill_per_second
