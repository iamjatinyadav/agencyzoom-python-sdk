"""Concurrency primitives for the sync client (hand-written twin of ``_async/_compat.py``)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

__all__ = ["Lock", "run_blocking", "sleep"]

T = TypeVar("T")

Lock = threading.Lock
sleep = time.sleep


def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    return func(*args, **kwargs)
