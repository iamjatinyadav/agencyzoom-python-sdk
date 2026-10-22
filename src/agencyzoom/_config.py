"""Client configuration: constructor arguments merged with environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping

import httpx

from ._exceptions import ConfigurationError

__all__ = [
    "DEFAULT_API_VERSION",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "ClientOptions",
    "RetryConfig",
]

DEFAULT_BASE_URL = "https://api.agencyzoom.com"
DEFAULT_API_VERSION = "v1"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
#: AgencyZoom's documented limit (as of 2026-08-17) is 120 calls per minute.
DEFAULT_RATE_LIMIT_PER_MINUTE = 120

ENV_USERNAME = "AGENCYZOOM_USERNAME"
ENV_PASSWORD = "AGENCYZOOM_PASSWORD"
ENV_TOKEN = "AGENCYZOOM_TOKEN"
ENV_API_TOKEN = "AGENCYZOOM_API_TOKEN"
ENV_BASE_URL = "AGENCYZOOM_BASE_URL"
ENV_API_VERSION = "AGENCYZOOM_API_VERSION"

_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _default_retry_statuses() -> frozenset[int]:
    return frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryConfig:
    """How failed requests are retried.

    * ``429`` responses and connection errors are always safe to retry, because the
      server never processed the request.
    * Other ``retry_statuses`` (5xx) are only retried for idempotent methods
      (GET/PUT/DELETE/HEAD/OPTIONS) to avoid creating duplicate records.
    """

    max_retries: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 30.0
    retry_statuses: frozenset[int] = field(default_factory=_default_retry_statuses)
    respect_retry_after: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_retries, bool) or self.max_retries < 0:
            raise ConfigurationError("max_retries must be an integer >= 0")
        if self.backoff_factor < 0 or self.max_backoff < 0:
            raise ConfigurationError("backoff values must be >= 0")


@dataclass(frozen=True)
class ClientOptions:
    """Fully-resolved, immutable client settings."""

    base_url: str
    api_root: str
    endpoint_overrides: Mapping[str, str]
    username: str | None
    # Secrets are excluded from repr() so they can't leak into logs or tracebacks.
    password: str | None = field(repr=False)
    token: str | None = field(repr=False)
    refresh_token: str | None = field(repr=False)
    api_token: str | None = field(repr=False)
    timeout: httpx.Timeout
    retry: RetryConfig
    rate_limit_per_minute: float | None
    cache_ttl: float | None
    user_agent: str
    default_headers: dict[str, str]

    @classmethod
    def resolve(
        cls,
        *,
        base_url: str | None,
        api_version: str | None,
        api_root: str | None,
        endpoint_overrides: Mapping[str, str] | None,
        username: str | None,
        password: str | None,
        token: str | None,
        refresh_token: str | None,
        api_token: str | None,
        timeout: float | httpx.Timeout | None,
        max_retries: int | RetryConfig,
        rate_limit_per_minute: float | None,
        cache_ttl: float | None,
        default_headers: Mapping[str, str] | None,
        user_agent: str,
    ) -> ClientOptions:
        username = username or _env(ENV_USERNAME)
        password = password or _env(ENV_PASSWORD)
        token = token or _env(ENV_TOKEN)

        if not token and not (username and password):
            raise ConfigurationError(
                "No AgencyZoom credentials found. Pass `username` and `password` "
                f"(or `token`), or set {ENV_USERNAME}/{ENV_PASSWORD} (or {ENV_TOKEN})."
            )
        if bool(username) != bool(password):
            raise ConfigurationError("`username` and `password` must be provided together.")

        resolved_base_url = (
            (_blank(base_url) or _env(ENV_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/")
        )
        if not resolved_base_url.startswith(("https://", "http://")):
            raise ConfigurationError(
                f"base_url must start with https:// (or http://), got {resolved_base_url!r}"
            )

        version = (
            (_blank(api_version) or _env(ENV_API_VERSION) or DEFAULT_API_VERSION).strip().strip("/")
        )
        if not _VERSION_RE.match(version):
            raise ConfigurationError(f"Invalid api_version {version!r} (expected e.g. 'v1').")
        root = api_root if api_root is not None else f"/{version}/api"

        return cls(
            base_url=resolved_base_url,
            api_root=root,
            endpoint_overrides=dict(endpoint_overrides or {}),
            username=username,
            password=password,
            token=token,
            refresh_token=refresh_token,
            api_token=api_token or _env(ENV_API_TOKEN),
            timeout=resolve_timeout(timeout),
            retry=resolve_retry(max_retries),
            rate_limit_per_minute=_positive_or_none("rate_limit_per_minute", rate_limit_per_minute),
            cache_ttl=_positive_or_none("cache_ttl", cache_ttl),
            user_agent=user_agent,
            default_headers=dict(default_headers or {}),
        )


def resolve_timeout(timeout: float | httpx.Timeout | None) -> httpx.Timeout:
    if timeout is None:
        return DEFAULT_TIMEOUT
    if isinstance(timeout, httpx.Timeout):
        return timeout
    if isinstance(timeout, bool) or timeout <= 0:
        raise ConfigurationError(f"timeout must be a positive number of seconds, got {timeout!r}")
    return httpx.Timeout(float(timeout))


def resolve_retry(max_retries: int | RetryConfig) -> RetryConfig:
    if isinstance(max_retries, RetryConfig):
        return max_retries
    return RetryConfig(max_retries=max_retries)


def _positive_or_none(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{name} must be > 0, or None to disable; got {value!r}")
    return float(value)


def _blank(value: str | None) -> str | None:
    return value if value and value.strip() else None


def _env(name: str) -> str | None:
    """An environment variable, treating unset and blank values the same."""
    return _blank(os.environ.get(name))
