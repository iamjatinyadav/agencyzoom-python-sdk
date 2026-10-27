"""Concurrency primitives for the async client.

``_sync/_compat.py`` is the hand-written blocking twin of this module; everything
else under ``_sync/`` is generated from ``_async/`` by ``scripts/unasync.py``.
"""

from __future__ import annotations

import asyncio
import functools
from types import TracebackType
from typing import Any, Callable, TypeVar

from .._exceptions import AgencyZoomError

__all__ = ["Lock", "LoopGuard", "run_blocking", "sleep"]

T = TypeVar("T")

sleep = asyncio.sleep


class LoopGuard:
    """Bind on first use and reject reuse from a different event loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    def check(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise AgencyZoomError(
                "Use an AsyncAgencyZoom client in one event loop; create a new client for this loop."
            )


class Lock:
    """An asyncio lock created lazily in the client's event loop."""

    __slots__ = ("_guard", "_lock")

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._guard = LoopGuard()

    async def __aenter__(self) -> None:
        self._guard.check()
        if self._lock is None:
            self._lock = asyncio.Lock()
        await self._lock.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._lock is not None
        self._lock.release()


async def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking work (e.g. reading upload files) without stalling the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
