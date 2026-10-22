"""I/O-free helpers shared by the sync and async clients."""

from __future__ import annotations

import copy
import logging
import mimetypes
import os
import re
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import (
    IO,
    Any,
    Hashable,
    Mapping,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    get_origin,
    overload,
)

from pydantic import BaseModel, TypeAdapter, ValidationError

__all__ = [
    "FileInput",
    "TTLCache",
    "build_body",
    "parse_response",
    "prepare_files",
    "redact_headers",
]

logger = logging.getLogger("agencyzoom")

M = TypeVar("M", bound=BaseModel)
T = TypeVar("T")

#: A file to upload: a path, raw bytes, an open file, or an explicit
#: ``(filename, content)`` / ``(filename, content, content_type)`` tuple.
FileContent = Union[bytes, str, IO[bytes], IO[str]]
FileInput = Union[
    str,
    "os.PathLike[str]",
    bytes,
    IO[bytes],
    IO[str],
    Tuple[str, FileContent],
    Tuple[str, FileContent, str],
]
PreparedFile = Tuple[str, Tuple[str, bytes, str]]

_SENSITIVE_HEADERS = frozenset({"authorization", "x-api-token", "cookie", "set-cookie"})


# --------------------------------------------------------------------------- requests


def build_body(
    model: type[M], body: M | Mapping[str, Any] | None, fields: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge ``body`` and keyword ``fields``, validate them against ``model`` and
    return the camelCase JSON payload.

    Accepts snake_case or camelCase keys, so all of these are equivalent::

        build_body(LeadSearchRequest, None, {"page_size": 50})
        build_body(LeadSearchRequest, {"pageSize": 50}, {})
        build_body(LeadSearchRequest, LeadSearchRequest(page_size=50), {})
    """
    if isinstance(body, BaseModel):
        data: dict[str, Any] = body.model_dump(by_alias=True, exclude_unset=True)
    elif body is None:
        data = {}
    elif isinstance(body, Mapping):
        data = dict(body)
    else:
        raise TypeError(
            f"body must be a {model.__name__}, a mapping or None, not {type(body).__name__}"
        )
    # Normalise snake_case keys to API aliases first, so that keyword arguments
    # reliably override the same field given in `body` under either spelling.
    aliases = _field_aliases(model)
    merged = {aliases.get(k, k): v for k, v in data.items()}
    merged.update({aliases.get(k, k): v for k, v in fields.items()})
    return model.model_validate(merged).model_dump(mode="json", by_alias=True, exclude_unset=True)


@lru_cache(maxsize=512)
def _field_aliases(model: type[BaseModel]) -> dict[str, str]:
    return {name: f.alias or name for name, f in model.model_fields.items()}


def prepare_files(files: FileInput | Sequence[FileInput]) -> list[PreparedFile]:
    """Normalise upload inputs into in-memory multipart parts.

    Contents are read eagerly so the request body can be replayed on retry.
    """
    items: Sequence[Any]
    if isinstance(files, (str, bytes, os.PathLike, tuple)) or hasattr(files, "read"):
        items = [files]
    else:
        items = list(files)
    if not items:
        raise ValueError("At least one file is required for upload.")
    return [("files", _prepare_one(item, index)) for index, item in enumerate(items)]


def _prepare_one(item: Any, index: int) -> tuple[str, bytes, str]:
    content_type: str | None = None
    if isinstance(item, tuple):
        if len(item) not in (2, 3):
            raise ValueError("File tuples must be (name, content) or (name, content, content_type)")
        name, content = str(item[0]), item[1]
        content_type = item[2] if len(item) == 3 else None
        data = _to_bytes(content.read() if hasattr(content, "read") else content)
    elif isinstance(item, (str, os.PathLike)):
        path = Path(item)
        if not path.is_file():
            raise FileNotFoundError(f"Upload file not found: {path}")
        name, data = path.name, path.read_bytes()
    elif isinstance(item, (bytes, bytearray, memoryview)):
        name, data = f"file-{index}", bytes(item)
    elif hasattr(item, "read"):
        name = Path(str(getattr(item, "name", "") or f"file-{index}")).name
        data = _to_bytes(item.read())
    else:
        raise TypeError(f"Unsupported upload input: {type(item).__name__}")
    name = name or f"file-{index}"
    content_type = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    return name, data, content_type


def _to_bytes(content: Any) -> bytes:
    if isinstance(content, str):  # file opened in text mode
        return content.encode("utf-8")
    if isinstance(content, (bytes, bytearray, memoryview)):
        return bytes(content)
    raise TypeError(f"File content must be bytes or str, not {type(content).__name__}")


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()}


# --------------------------------------------------------------------------- responses


@lru_cache(maxsize=256)
def _adapter(tp: Any) -> TypeAdapter[Any]:
    return TypeAdapter(tp)


@overload
def parse_response(cast_to: type[T], data: Any) -> T: ...
@overload
def parse_response(cast_to: object, data: Any) -> Any: ...
def parse_response(cast_to: Any, data: Any) -> Any:
    """Validate ``data`` into ``cast_to`` (a model, ``List[Model]``, or any type).

    AgencyZoom's payloads don't always match its own spec. Rather than failing a
    successful call over one malformed field, invalid fields are set to ``None``
    (with a warning) and validation is retried; the raw payload is returned only
    if that also fails.
    """
    if cast_to is None or data is None:
        return data
    adapter = _adapter(cast_to)
    ignored: dict[str, str] = {}  # field path -> pydantic error type, insertion-ordered
    copied = False
    # Each pass nulls *every* invalid field; extra passes only handle errors that
    # surface once earlier ones are fixed (e.g. inside unions).
    for _ in range(10):
        try:
            result = adapter.validate_python(data)
        except ValidationError as exc:
            if not copied:
                data = copy.deepcopy(data)  # never mutate the caller's (possibly cached) payload
                copied = True
            fixed = False
            for err in exc.errors(include_url=False, include_input=False):
                path = _null_out(data, err["loc"])
                if path is not None:
                    fixed = True
                    ignored.setdefault(_display_path(path), err["type"])
            if not fixed:
                break
        else:
            if ignored:
                logger.warning(
                    "AgencyZoom response for %s didn't match its spec; set to None: %s",
                    _type_name(cast_to),
                    ", ".join(f"{path} ({kind})" for path, kind in ignored.items()),
                )
            return result
    logger.warning("Returning unvalidated AgencyZoom response for %s", _type_name(cast_to))
    return data


def invalid_fields(cast_to: Any, data: Any) -> list[tuple[str, str, str, Any]]:
    """``(path, error_type, message, raw_value)`` for each field of ``data`` that
    doesn't fit ``cast_to``. Used by diagnostics; doesn't modify ``data``."""
    try:
        _adapter(cast_to).validate_python(data)
    except ValidationError as exc:
        found = []
        for err in exc.errors(include_url=False, include_input=False):
            path, value = _locate(data, err["loc"])
            found.append((_display_path(path), err["type"], err["msg"], value))
        return found
    return []


def _locate(data: Any, loc: tuple[int | str, ...]) -> tuple[tuple[int | str, ...], Any]:
    """Follow ``loc`` through the payload, skipping segments that aren't in it
    (pydantic adds union-member tags like ``list[Model]`` to error locations)."""
    path: list[int | str] = []
    node = data
    for part in loc:
        in_dict = isinstance(node, dict) and part in node
        in_list = isinstance(node, list) and isinstance(part, int) and 0 <= part < len(node)
        if in_dict or in_list:
            node = node[part]
            path.append(part)
    return tuple(path), node


def _null_out(data: Any, loc: tuple[int | str, ...]) -> tuple[int | str, ...] | None:
    """Set the deepest dict field addressed by ``loc`` to ``None``; return its path."""
    path, _ = _locate(data, loc)
    # Walk back to the last dict key: list items themselves can't be nulled
    # (a list[int] can't hold None), so null the field that holds the list.
    while path and not isinstance(path[-1], str):
        path = path[:-1]
    if not path:
        return None
    _, parent = _locate(data, path[:-1])
    key = path[-1]
    if not isinstance(parent, dict) or parent.get(key) is None:
        return None
    parent[key] = None
    return path


def _display_path(path: tuple[int | str, ...]) -> str:
    """``("items", 3, "dueDate")`` -> ``"items[].dueDate"`` (indices collapsed, so
    one bad field reported across 50 list items appears once)."""
    text = ""
    for part in path:
        text += "[]" if isinstance(part, int) else (f".{part}" if text else str(part))
    return text or "<root>"


def _type_name(tp: Any) -> str:
    """``LeadDetail``, ``List[Note]``, ``Union[List[WrittenPolicy], WrittenPolicy]``."""
    if get_origin(tp) is None and hasattr(tp, "__name__"):
        return str(tp.__name__)
    return re.sub(r"\b(?:typing|agencyzoom\.models\._generated)\.", "", str(tp))


# --------------------------------------------------------------------------- caching


class TTLCache:
    """A tiny, thread-safe, time-based cache for slowly-changing reference data."""

    __slots__ = ("_data", "_lock", "_max_entries", "_ttl")

    def __init__(self, ttl: float, max_entries: int = 256) -> None:
        self._ttl = ttl
        self._max_entries = max_entries
        self._data: dict[Hashable, tuple[float, Any]] = {}
        # Never held across an await, so it is safe for the async client too.
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> tuple[bool, Any]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._data[key]
                return False, None
            return True, value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            if key not in self._data and len(self._data) >= self._max_entries:
                self._data.pop(next(iter(self._data)))  # evict the oldest entry
            self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
