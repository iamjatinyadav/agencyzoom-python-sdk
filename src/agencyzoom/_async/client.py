"""The public async client."""

from __future__ import annotations

import dataclasses
from functools import cached_property
from types import TracebackType
from typing import Any, Mapping

import httpx

from .._config import (
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    ClientOptions,
    RetryConfig,
    resolve_api_version,
    resolve_base_url,
    resolve_retry,
    resolve_timeout,
)
from .._endpoints import EndpointResolver
from .._exceptions import ConfigurationError
from .._version import __version__
from ._http import AsyncHTTPClient
from .resources import (
    AsyncAuth,
    AsyncBusinessClassifications,
    AsyncContacts,
    AsyncCustomers,
    AsyncDashboard,
    AsyncDepartments,
    AsyncEmailThreads,
    AsyncLeads,
    AsyncLifeHealth,
    AsyncOpportunities,
    AsyncPipelines,
    AsyncPolicies,
    AsyncProfile,
    AsyncServiceTickets,
    AsyncSettings,
    AsyncTasks,
    AsyncTextThreads,
    AsyncV4SSO,
)

__all__ = ["AsyncAgencyZoom"]


class AsyncAgencyZoom:
    """Client for the AgencyZoom REST API.

    Credentials are taken from the arguments or from the ``AGENCYZOOM_USERNAME`` /
    ``AGENCYZOOM_PASSWORD`` (or ``AGENCYZOOM_TOKEN``) environment variables. The
    client logs in lazily on the first request and keeps the token fresh.

    Use it as a context manager (or call ``close()``) to release connections.

    Args:
        username: AgencyZoom login email. Use the agency owner for full access.
        password: AgencyZoom password.
        token: An existing JWT, instead of username/password.
        refresh_token: Refresh token accompanying ``token``, enabling renewal.
        api_token: ``X-Api-Token`` value, required only by ``policies.create``.
        base_url: Override the API host (e.g. for a proxy or test server).
        api_version: API version used in every path (``/{api_version}/api/...``).
            Defaults to ``"v1"`` or ``AGENCYZOOM_API_VERSION``.
        api_root: Replace the whole path prefix (e.g. ``"/api/v2"``); wins over
            ``api_version``.
        endpoint_overrides: Move individual endpoints, keyed by endpoint ID:
            ``{"leads.search": "POST /v2/api/leads/search"}``. See ``agencyzoom.ENDPOINTS``.
        timeout: Seconds, or an ``httpx.Timeout``. Defaults to 60s (10s connect).
        max_retries: Retry count, or a :class:`RetryConfig` for full control.
        rate_limit_per_minute: Client-side request budget; ``None`` disables it.
            Defaults to AgencyZoom's documented limit of 120/minute.
        cache_ttl: Seconds to cache reference data (``client.settings``,
            ``client.pipelines``). ``None`` (default) disables caching.
        default_headers: Extra headers sent with every request.
        http_client: Bring your own ``httpx`` client (proxies, custom TLS, hooks...).
            It is not closed by this client.
        http2: Enable HTTP/2 (requires ``pip install agencyzoom-sdk[http2]``).
        strict_response_validation: Raise ``APIResponseError`` on response model
            mismatches instead of repairing fields or returning raw JSON.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        token: str | None = None,
        refresh_token: str | None = None,
        api_token: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        api_root: str | None = None,
        endpoint_overrides: Mapping[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | RetryConfig = 3,
        rate_limit_per_minute: float | None = DEFAULT_RATE_LIMIT_PER_MINUTE,
        cache_ttl: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        http2: bool = False,
        strict_response_validation: bool = False,
    ) -> None:
        options = ClientOptions.resolve(
            base_url=base_url,
            api_version=api_version,
            api_root=api_root,
            endpoint_overrides=endpoint_overrides,
            username=username,
            password=password,
            token=token,
            refresh_token=refresh_token,
            api_token=api_token,
            timeout=timeout,
            max_retries=max_retries,
            rate_limit_per_minute=rate_limit_per_minute,
            cache_ttl=cache_ttl,
            default_headers=default_headers,
            user_agent=f"agencyzoom-python-sdk/{__version__}",
            strict_response_validation=strict_response_validation,
        )
        self._http = AsyncHTTPClient(options, http_client=http_client, http2=http2)

    # ------------------------------------------------------------------ resources

    @cached_property
    def auth(self) -> AsyncAuth:
        return AsyncAuth(self._http)

    @cached_property
    def v4sso(self) -> AsyncV4SSO:
        return AsyncV4SSO(self._http)

    @cached_property
    def leads(self) -> AsyncLeads:
        return AsyncLeads(self._http)

    @cached_property
    def customers(self) -> AsyncCustomers:
        return AsyncCustomers(self._http)

    @cached_property
    def policies(self) -> AsyncPolicies:
        return AsyncPolicies(self._http)

    @cached_property
    def opportunities(self) -> AsyncOpportunities:
        return AsyncOpportunities(self._http)

    @cached_property
    def tasks(self) -> AsyncTasks:
        return AsyncTasks(self._http)

    @cached_property
    def service_tickets(self) -> AsyncServiceTickets:
        return AsyncServiceTickets(self._http)

    @cached_property
    def email_threads(self) -> AsyncEmailThreads:
        return AsyncEmailThreads(self._http)

    @cached_property
    def text_threads(self) -> AsyncTextThreads:
        return AsyncTextThreads(self._http)

    @cached_property
    def contacts(self) -> AsyncContacts:
        return AsyncContacts(self._http)

    @cached_property
    def life_health(self) -> AsyncLifeHealth:
        return AsyncLifeHealth(self._http)

    @cached_property
    def dashboard(self) -> AsyncDashboard:
        return AsyncDashboard(self._http)

    @cached_property
    def profile(self) -> AsyncProfile:
        return AsyncProfile(self._http)

    @cached_property
    def settings(self) -> AsyncSettings:
        return AsyncSettings(self._http)

    @cached_property
    def pipelines(self) -> AsyncPipelines:
        return AsyncPipelines(self._http)

    @cached_property
    def departments(self) -> AsyncDepartments:
        return AsyncDepartments(self._http)

    @cached_property
    def business_classifications(self) -> AsyncBusinessClassifications:
        return AsyncBusinessClassifications(self._http)

    # ------------------------------------------------------------------ flexibility

    def with_options(
        self,
        *,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | RetryConfig | None = None,
        default_headers: Mapping[str, str] | None = None,
        base_url: str | None = None,
        api_root: str | None = None,
        api_version: str | None = None,
        endpoint_overrides: Mapping[str, str] | None = None,
        api_token: str | None = None,
        strict_response_validation: bool | None = None,
    ) -> AsyncAgencyZoom:
        """Return a client with some options changed, e.g. for a single slow call::

            await client.with_options(timeout=120, max_retries=0).leads.batch_create(...)

        The copy shares connections, the login session, the rate limiter and the
        cache with this client, so it's cheap. Headers and endpoint overrides are
        merged with the current ones; closing either client closes both.
        """
        current = self._http.options
        changes: dict[str, Any] = {}
        if timeout is not None:
            changes["timeout"] = resolve_timeout(timeout)
        if max_retries is not None:
            changes["retry"] = resolve_retry(max_retries)
        if default_headers is not None:
            changes["default_headers"] = {**current.default_headers, **default_headers}
        if base_url is not None:
            changes["base_url"] = resolve_base_url(base_url)
        if api_root is not None:
            changes["api_root"] = api_root
        elif api_version is not None:
            changes["api_root"] = f"/{resolve_api_version(api_version)}/api"
        if endpoint_overrides is not None:
            changes["endpoint_overrides"] = {**current.endpoint_overrides, **endpoint_overrides}
        if api_token is not None:
            changes["api_token"] = api_token
        if strict_response_validation is not None:
            if not isinstance(strict_response_validation, bool):
                raise ConfigurationError("strict_response_validation must be a boolean")
            changes["strict_response_validation"] = strict_response_validation
        options = dataclasses.replace(current, **changes)
        EndpointResolver(options.api_root, options.endpoint_overrides)  # validate eagerly

        clone = object.__new__(type(self))
        clone._http = self._http.copy(options)
        return clone

    # ------------------------------------------------------------------ escape hatch

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cast_to: Any = None,
    ) -> Any:
        """Call any endpoint directly (e.g. one added after this SDK was released),
        with the same auth, retries and rate limiting as the typed methods.

        ``path`` is used as-is from the host root, e.g. ``"/v2/api/leads/list"``.
        """
        return await self._http.request(method, path, params=params, json=json, cast_to=cast_to)

    def clear_cache(self) -> None:
        """Drop cached reference data."""
        self._http.clear_cache()

    # ------------------------------------------------------------------ lifecycle

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> AsyncAgencyZoom:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self._http.options.base_url!r})"
