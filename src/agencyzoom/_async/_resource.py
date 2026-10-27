"""Base class for API resource groups (``client.leads``, ``client.tasks``, ...)."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, List, Mapping, TypeVar, overload

from .._exceptions import APIResponseError
from .._utils import PreparedFile, parse_response
from ._http import AsyncHTTPClient

__all__ = ["AsyncAPIResource"]

T = TypeVar("T")

logger = logging.getLogger("agencyzoom")

#: Safety valve against runaway pagination.
MAX_PAGES = 10_000


class AsyncAPIResource:
    """Typed access to registered endpoints.

    Passing ``cast_to=SomeModel`` (or ``List[SomeModel]``) validates the response
    into that type, and ``_call`` is typed to return it.
    """

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    @overload
    async def _call(
        self,
        endpoint_id: str,
        *,
        path_params: Mapping[str, object] | None = ...,
        params: Mapping[str, Any] | None = ...,
        body: Any = ...,
        data: Mapping[str, Any] | None = ...,
        files: list[PreparedFile] | None = ...,
        headers: Mapping[str, str] | None = ...,
        cast_to: type[T],
        authenticated: bool = ...,
        cache: bool = ...,
    ) -> T: ...
    @overload
    async def _call(
        self,
        endpoint_id: str,
        *,
        path_params: Mapping[str, object] | None = ...,
        params: Mapping[str, Any] | None = ...,
        body: Any = ...,
        data: Mapping[str, Any] | None = ...,
        files: list[PreparedFile] | None = ...,
        headers: Mapping[str, str] | None = ...,
        cast_to: object = ...,
        authenticated: bool = ...,
        cache: bool = ...,
    ) -> Any: ...
    async def _call(
        self,
        endpoint_id: str,
        *,
        path_params: Mapping[str, object] | None = None,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[PreparedFile] | None = None,
        headers: Mapping[str, str] | None = None,
        cast_to: object = None,
        authenticated: bool = True,
        cache: bool = False,
    ) -> Any:
        return await self._http.call(
            endpoint_id,
            path_params=path_params,
            params=params,
            json=body,
            data=data,
            files=files,
            headers=headers,
            cast_to=cast_to,
            authenticated=authenticated,
            cache=cache,
        )

    async def _paginate(
        self,
        endpoint_id: str,
        body: dict[str, Any],
        *,
        items_key: str,
        item_type: type[T],
        page_size: int,
    ) -> AsyncIterator[T]:
        """Yield every item of a paged ``POST`` search, fetching pages lazily.

        Stops at ``totalCount``, or a short/empty page when no total is supplied.
        Malformed, repeated or prematurely empty pages and exhaustion of the page
        limit raise ``APIResponseError`` so incomplete exports cannot pass silently.
        """
        size = body.get("pageSize") if body.get("pageSize") is not None else page_size
        page = body.get("page") if body.get("page") is not None else 0
        if type(size) is not int or size <= 0 or type(page) is not int or page < 0:
            raise ValueError(
                "pageSize must be a positive integer and page must be a non-negative integer"
            )
        body = {**body, "pageSize": size}
        seen = page * size
        previous: list[Any] | None = None
        for _ in range(MAX_PAGES):
            payload = await self._http.call(endpoint_id, json={**body, "page": page})
            if not isinstance(payload, dict):
                raise APIResponseError(f"{endpoint_id}: expected a pagination object", body=payload)
            raw_items = payload.get(items_key)
            if not isinstance(raw_items, list) or any(
                not isinstance(item, dict) for item in raw_items
            ):
                raise APIResponseError(
                    f"{endpoint_id}: expected a list of objects in {items_key}", body=payload
                )
            total = _as_int(payload.get("totalCount"))
            if payload.get("totalCount") is not None and (total is None or total < 0):
                raise APIResponseError(f"{endpoint_id}: invalid totalCount", body=payload)
            if not raw_items:
                if total is not None and seen < total:
                    raise APIResponseError(
                        f"{endpoint_id}: empty page before totalCount was reached", body=payload
                    )
                return
            if raw_items == previous:
                raise APIResponseError(f"{endpoint_id}: returned the same page twice", body=payload)
            previous = raw_items
            item_list_type = List[item_type]  # type: ignore[valid-type]
            items: list[T] = parse_response(
                item_list_type,
                raw_items,
                strict=self._http.options.strict_response_validation,
            )
            for item in items:
                yield item
            seen += len(items)
            if (total is None and len(items) < size) or (total is not None and seen >= total):
                return
            page += 1
        raise APIResponseError(
            f"{endpoint_id}: pagination exceeded the safety limit of {MAX_PAGES} pages"
        )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
