"""The transport layer: every API call goes through :meth:`AsyncHTTPClient.request`."""

from __future__ import annotations

import hashlib
import json as jsonlib
import logging
import time
from typing import Any, Mapping

import httpx

from .._config import ClientOptions
from .._endpoints import EndpointResolver
from .._exceptions import (
    AgencyZoomError,
    APIConnectionError,
    APIResponseError,
    APITimeoutError,
    make_status_error,
)
from .._rate_limit import TokenBucket
from .._retry import IDEMPOTENT_METHODS, compute_backoff, should_retry_status
from .._utils import PreparedFile, TTLCache, parse_response, redact_headers
from ._auth import AsyncTokenManager
from ._compat import Lock, LoopGuard, sleep

__all__ = ["AsyncHTTPClient", "AsyncRateLimiter"]

logger = logging.getLogger("agencyzoom")

DEFAULT_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30)

# Errors raised before the request reached the server: always safe to retry.
_PRE_SEND_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class AsyncRateLimiter:
    """Spaces requests out so the client stays under AgencyZoom's per-minute quota."""

    def __init__(self, per_minute: float) -> None:
        self._bucket = TokenBucket(per_minute)
        self._lock = Lock()

    async def acquire(self) -> None:
        async with self._lock:
            delay = self._bucket.reserve()
        if delay > 0:
            logger.debug("Rate limiter: waiting %.2fs", delay)
            await sleep(delay)


class _Transport:
    """State shared between a client and every ``with_options()`` copy of it."""

    def __init__(self, client: httpx.AsyncClient, owns_client: bool) -> None:
        self.client = client
        self.owns_client = owns_client
        self.closed = False
        self.loop_guard = LoopGuard()


class AsyncHTTPClient:
    def __init__(
        self,
        options: ClientOptions,
        *,
        http_client: httpx.AsyncClient | None = None,
        http2: bool = False,
    ) -> None:
        self.options = options
        self.resolver = EndpointResolver(options.api_root, options.endpoint_overrides)
        self._transport = _Transport(
            http_client
            or httpx.AsyncClient(
                timeout=options.timeout,
                limits=DEFAULT_LIMITS,
                http2=http2,
                follow_redirects=False,
            ),
            owns_client=http_client is None,
        )
        self._limiter = (
            AsyncRateLimiter(options.rate_limit_per_minute)
            if options.rate_limit_per_minute
            else None
        )
        self._cache = TTLCache(options.cache_ttl) if options.cache_ttl else None
        self.auth = AsyncTokenManager(options, self._send_unauthenticated_json)

    def copy(self, options: ClientOptions) -> AsyncHTTPClient:
        """A client with different options that shares connections, auth, rate limit and cache."""
        clone = object.__new__(type(self))
        clone.options = options
        clone.resolver = EndpointResolver(options.api_root, options.endpoint_overrides)
        clone._transport = self._transport
        clone._limiter = self._limiter
        clone._cache = self._cache
        clone.auth = self.auth.copy(clone._send_unauthenticated_json)
        return clone

    @property
    def closed(self) -> bool:
        return self._transport.closed

    # ------------------------------------------------------------------ public

    async def call(
        self,
        endpoint_id: str,
        *,
        path_params: Mapping[str, object] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[PreparedFile] | None = None,
        headers: Mapping[str, str] | None = None,
        cast_to: Any = None,
        authenticated: bool = True,
        cache: bool = False,
    ) -> Any:
        """Call a registered endpoint by ID (see ``agencyzoom._endpoints``)."""
        method, path = self.resolver.resolve(endpoint_id, path_params)
        return await self.request(
            method,
            path,
            params=params,
            json=json,
            data=data,
            files=files,
            headers=headers,
            cast_to=cast_to,
            authenticated=authenticated,
            cache=cache,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[PreparedFile] | None = None,
        headers: Mapping[str, str] | None = None,
        cast_to: Any = None,
        authenticated: bool = True,
        cache: bool = False,
    ) -> Any:
        """Send a request and return the parsed (and optionally validated) body."""
        self._check_open()
        method = method.upper()
        if not path.startswith("/"):
            path = f"/{path}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cache_key = None
        revision = self.auth.revision
        cache_revision = self.auth.cache_revision
        if cache and self._cache is not None:
            if authenticated:
                await self.auth.get_token()
            revision = self.auth.revision
            cache_revision = self.auth.cache_revision
            # Headers may select a tenant. Hash them to avoid retaining secrets
            # in printable cache keys; session revisions isolate account changes.
            header_key = hashlib.sha256(
                jsonlib.dumps(
                    {
                        k.lower(): v
                        for k, v in {**self.options.default_headers, **(headers or {})}.items()
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            cache_key = (
                self.options.base_url,
                method,
                path,
                header_key,
                cache_revision,
                jsonlib.dumps(params, sort_keys=True, default=str),
            )
            hit, payload = self._cache.get(cache_key)
            if hit and cache_revision == self.auth.cache_revision:
                logger.debug("Cache hit: %s %s", method, path)
                return parse_response(
                    cast_to, payload, strict=self.options.strict_response_validation
                )

        response = await self._send(
            method,
            path,
            params=params,
            json=json,
            data=data,
            files=files,
            headers=headers,
            authenticated=authenticated,
        )
        payload = _decode(response, expect_json=cast_to is not None)
        if (
            cache_key is not None
            and self._cache is not None
            and revision == self.auth.revision
            and cache_revision == self.auth.cache_revision
        ):
            self._cache.set(cache_key, payload)
        return parse_response(cast_to, payload, strict=self.options.strict_response_validation)

    def clear_cache(self) -> None:
        if self._cache is not None:
            self._cache.clear()

    async def close(self) -> None:
        transport = self._transport
        if transport.closed:
            return
        transport.loop_guard.check()
        transport.closed = True
        if transport.owns_client:
            await transport.client.aclose()

    # ------------------------------------------------------------------ internals

    def _check_open(self) -> None:
        if self._transport.closed:
            raise AgencyZoomError("This AgencyZoom client has been closed; create a new one.")
        self._transport.loop_guard.check()

    async def _send_unauthenticated_json(
        self, endpoint_id: str, body: Mapping[str, Any] | None, token: str | None = None
    ) -> Any:
        method, path = self.resolver.resolve(endpoint_id)
        response = await self._send(
            method,
            path,
            json=body,
            authenticated=False,
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )
        return _decode(response, expect_json=True)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[PreparedFile] | None = None,
        headers: Mapping[str, str] | None = None,
        authenticated: bool = True,
    ) -> httpx.Response:
        self._check_open()
        options = self.options
        retry = options.retry
        url = f"{options.base_url}{path}"
        attempt = 0
        reauthenticated = False
        request_identity = self.auth.identity

        while True:
            self._check_open()
            if authenticated and request_identity != self.auth.identity:
                raise AgencyZoomError(
                    "The authenticated account changed during the request; it was not retried."
                )
            request_headers = httpx.Headers(
                {
                    "Accept": "application/json",
                    "User-Agent": options.user_agent,
                    **options.default_headers,
                    **(headers or {}),
                }
            )
            token: str | None = None
            identity = self.auth.identity
            if authenticated:
                token = await self.auth.get_token()
                request_headers["Authorization"] = f"Bearer {token}"

            if self._limiter is not None:
                await self._limiter.acquire()

            started = time.perf_counter()
            try:
                response = await self._transport.client.request(
                    method,
                    url,
                    params=params or None,
                    json=json,
                    data=data,
                    files=files,
                    headers=request_headers,
                    timeout=options.timeout,
                    follow_redirects=False,  # also override a caller-supplied HTTP client's setting
                )
            except httpx.TransportError as exc:
                retryable = isinstance(exc, _PRE_SEND_ERRORS) or method in IDEMPOTENT_METHODS
                if retryable and attempt < retry.max_retries:
                    delay = compute_backoff(retry, attempt)
                    logger.info(
                        "%s %s failed (%s); retry %d/%d in %.2fs",
                        method, path, type(exc).__name__, attempt + 1, retry.max_retries, delay,
                    )  # fmt: skip
                    attempt += 1
                    await sleep(delay)
                    continue
                if isinstance(exc, httpx.TimeoutException):
                    raise APITimeoutError(
                        f"Request timed out: {method} {path}", request=exc.request
                    ) from exc
                raise APIConnectionError(
                    f"Connection error: {method} {path}: {exc}", request=exc.request
                ) from exc

            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.debug(
                "%s %s -> %d (%.0fms, attempt %d)",
                method, path, response.status_code, elapsed_ms, attempt + 1,
            )  # fmt: skip

            if response.is_success:
                return response

            if response.status_code == 401 and token is not None and not reauthenticated:
                reauthenticated = True
                if await self.auth.handle_unauthorized(token, identity):
                    logger.debug("Received 401; retrying with a renewed token")
                    continue

            if (
                should_retry_status(retry, method, response.status_code)
                and attempt < retry.max_retries
            ):
                delay = compute_backoff(retry, attempt, response)
                logger.info(
                    "%s %s returned %d; retry %d/%d in %.2fs",
                    method, path, response.status_code, attempt + 1, retry.max_retries, delay,
                )  # fmt: skip
                attempt += 1
                await sleep(delay)
                continue

            error = make_status_error(response)
            logger.debug(
                "AgencyZoom error %s for %s %s (headers=%s)",
                error, method, path, redact_headers(response.request.headers),
            )  # fmt: skip
            raise error


def _decode(response: httpx.Response, *, expect_json: bool) -> Any:
    if response.status_code == 204 or not response.content.strip():
        return None
    try:
        return response.json()
    except ValueError:
        if expect_json:
            # e.g. an HTML maintenance page or proxy error served with status 200.
            snippet = response.text.strip()[:200]
            raise APIResponseError(
                f"Expected JSON from {response.request.method} {response.request.url.path}, "
                f"got {response.headers.get('content-type', 'unknown content')}: {snippet!r}",
                response=response,
            ) from None
        return response.text
