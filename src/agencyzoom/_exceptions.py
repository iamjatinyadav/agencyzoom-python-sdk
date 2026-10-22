"""Exception hierarchy raised by the SDK.

All exceptions derive from :class:`AgencyZoomError`, so callers can catch a single
type. HTTP failures are mapped to a specific :class:`APIStatusError` subclass based
on the status code, and carry the parsed AgencyZoom error payload::

    AgencyZoomError
    ├── ConfigurationError
    ├── APIConnectionError
    │   └── APITimeoutError
    ├── APIResponseError               (2xx, but the body was unusable)
    └── APIStatusError
        ├── BadRequestError            (400)
        ├── AuthenticationError        (401)
        ├── PermissionDeniedError      (403)
        ├── NotFoundError              (404)
        ├── ConflictError              (409)
        ├── UnprocessableEntityError   (422)
        ├── RateLimitError             (429)
        └── InternalServerError        (5xx)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

__all__ = [
    "APIConnectionError",
    "APIResponseError",
    "APIStatusError",
    "APITimeoutError",
    "AgencyZoomError",
    "AuthenticationError",
    "BadRequestError",
    "ConfigurationError",
    "ConflictError",
    "FieldError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "UnprocessableEntityError",
]


class AgencyZoomError(Exception):
    """Base class for every error raised by this SDK."""


class ConfigurationError(AgencyZoomError):
    """The client was configured incorrectly (e.g. no credentials were supplied)."""


class APIConnectionError(AgencyZoomError):
    """The request never produced an HTTP response (DNS, TLS, connection reset...)."""

    def __init__(self, message: str, *, request: httpx.Request | None = None) -> None:
        super().__init__(message)
        self.request = request


class APITimeoutError(APIConnectionError):
    """The request timed out."""


class APIResponseError(AgencyZoomError):
    """The request succeeded, but the response could not be used.

    For example a non-JSON body (an HTML maintenance page served with status 200),
    or a login response without a token.
    """

    def __init__(
        self, message: str, *, response: httpx.Response | None = None, body: Any = None
    ) -> None:
        super().__init__(message)
        self.response = response
        self.body = body


@dataclass(frozen=True)
class FieldError:
    """A single field-level validation error returned by AgencyZoom."""

    field: str | None
    error: str | None


class APIStatusError(AgencyZoomError):
    """AgencyZoom answered with a non-2xx status code."""

    status_code: int

    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response,
        body: Any = None,
        field_errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.response = response
        self.status_code = response.status_code
        self.body = body
        self.field_errors: list[FieldError] = field_errors or []

    @property
    def request(self) -> httpx.Request:
        return self.response.request

    def __str__(self) -> str:
        base = f"[{self.status_code}] {self.message}"
        if self.field_errors:
            details = ", ".join(f"{e.field}: {e.error}" for e in self.field_errors)
            base = f"{base} ({details})"
        return base


class BadRequestError(APIStatusError):
    status_code = 400


class AuthenticationError(APIStatusError):
    status_code = 401


class PermissionDeniedError(APIStatusError):
    status_code = 403


class NotFoundError(APIStatusError):
    status_code = 404


class ConflictError(APIStatusError):
    status_code = 409


class UnprocessableEntityError(APIStatusError):
    status_code = 422


class RateLimitError(APIStatusError):
    status_code = 429


class InternalServerError(APIStatusError):
    pass


_STATUS_TO_ERROR: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}


def make_status_error(response: httpx.Response) -> APIStatusError:
    """Build the most specific :class:`APIStatusError` for ``response``."""
    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text or None

    message = f"HTTP {response.status_code} {response.reason_phrase}".strip()
    field_errors: list[FieldError] = []
    if isinstance(body, dict):
        message = str(body.get("error") or body.get("message") or message)
        raw_errors = body.get("fieldErrors")
        if isinstance(raw_errors, list):
            field_errors = [
                FieldError(field=e.get("field"), error=e.get("error"))
                for e in raw_errors
                if isinstance(e, dict)
            ]
    elif isinstance(body, str) and body.strip():
        message = body.strip()[:500]

    status = response.status_code
    error_cls = _STATUS_TO_ERROR.get(status)
    if error_cls is None:
        error_cls = InternalServerError if status >= 500 else APIStatusError
    return error_cls(message, response=response, body=body, field_errors=field_errors)
