"""Client configuration: constructor arguments merged with environment variables."""

from __future__ import annotations

import math
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
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ConfigurationError("max_retries must be an integer >= 0")
        _finite_number("backoff_factor", self.backoff_factor, allow_zero=True)
        _finite_number("max_backoff", self.max_backoff, allow_zero=True)
        if not isinstance(self.respect_retry_after, bool):
            raise ConfigurationError("respect_retry_after must be a boolean")
        try:
            statuses = frozenset(self.retry_statuses)
        except TypeError:
            raise ConfigurationError("retry_statuses must contain HTTP status integers") from None
        if any(type(code) is not int or not 100 <= code <= 599 for code in statuses):
            raise ConfigurationError("retry_statuses must contain HTTP status integers (100..599)")
        object.__setattr__(self, "retry_statuses", statuses)


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
    default_headers: dict[str, str] = field(repr=False)
    strict_response_validation: bool

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
        strict_response_validation: bool = False,
    ) -> ClientOptions:
        username = _blank(username) or _env(ENV_USERNAME)
        password = _blank(password) or _env(ENV_PASSWORD)
        token = _blank(token) or _env(ENV_TOKEN)
        if not isinstance(strict_response_validation, bool):
            raise ConfigurationError("strict_response_validation must be a boolean")

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
        resolved_base_url = resolve_base_url(resolved_base_url)

        version = (
            (_blank(api_version) or _env(ENV_API_VERSION) or DEFAULT_API_VERSION).strip().strip("/")
        )
        version = resolve_api_version(version)
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
            strict_response_validation=strict_response_validation,
        )


def resolve_timeout(timeout: float | httpx.Timeout | None) -> httpx.Timeout:
    if timeout is None:
        return DEFAULT_TIMEOUT
    if isinstance(timeout, httpx.Timeout):
        for name in ("connect", "read", "write", "pool"):
            value = getattr(timeout, name)
            if value is not None:
                _finite_number(f"timeout.{name}", value)
        return timeout
    return httpx.Timeout(_finite_number("timeout", timeout))


def resolve_retry(max_retries: int | RetryConfig) -> RetryConfig:
    if isinstance(max_retries, RetryConfig):
        return max_retries
    return RetryConfig(max_retries=max_retries)


def _positive_or_none(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    return _finite_number(name, value)


def _finite_number(name: str, value: object, *, allow_zero: bool = False) -> float:
    try:
        number = float(value) if isinstance(value, (int, float)) else float("nan")
    except (ValueError, OverflowError):
        number = float("nan")
    if (
        isinstance(value, bool)
        or not math.isfinite(number)
        or number < 0
        or (number == 0 and not allow_zero)
    ):
        raise ConfigurationError(
            f"{name} must be a finite number {'>= 0' if allow_zero else '> 0'}"
        )
    return number


def resolve_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        raise ConfigurationError("base_url must be a valid HTTP(S) URL") from None
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or url.query
        or url.fragment
    ):
        raise ConfigurationError(
            "base_url must be an HTTP(S) URL without credentials, query or fragment"
        )
    return value


def resolve_api_version(value: str) -> str:
    version = value.strip().strip("/")
    if not _VERSION_RE.fullmatch(version) or version in {".", ".."}:
        raise ConfigurationError("Invalid api_version (expected e.g. 'v1')")
    return version


def _blank(value: str | None) -> str | None:
    return value if value and value.strip() else None


def _env(name: str) -> str | None:
    """An environment variable, treating unset and blank values the same."""
    return _blank(os.environ.get(name))
