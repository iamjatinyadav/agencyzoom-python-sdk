"""Concurrency primitives for the async client.

``_sync/_compat.py`` is the hand-written blocking twin of this module; everything
else under ``_sync/`` is generated from ``_async/`` by ``scripts/unasync.py``.
"""

from __future__ import annotations

import asyncio
import functools
from types import TracebackType
from typing import Any, Callable, TypeVar

__all__ = ["Lock", "run_blocking", "sleep"]

T = TypeVar("T")

sleep = asyncio.sleep


class Lock:
    """An ``asyncio.Lock`` that binds to the running event loop lazily.

    Locks created outside a running loop (e.g. in ``__init__``) are bound to the
    wrong loop on Python < 3.10, and any asyncio lock fails if a client is reused
    under a new loop (successive ``asyncio.run()`` calls). This one is created on
    first use and recreated if the loop changes.
    """

    __slots__ = ("_lock", "_loop")

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def __aenter__(self) -> None:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock = asyncio.Lock()
            self._loop = loop
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
