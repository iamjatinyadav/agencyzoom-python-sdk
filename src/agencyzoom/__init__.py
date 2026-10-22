"""Unofficial Python SDK for the AgencyZoom REST API.

Quick start::

    from agencyzoom import AgencyZoom

    with AgencyZoom(username="owner@agency.com", password="...") as client:
        for lead in client.leads.paginate(status=0):
            print(lead.id, lead.firstname, lead.lastname)

``AsyncAgencyZoom`` offers the identical API with ``await``/``async for``.
"""

from . import models
from ._async.client import AsyncAgencyZoom
from ._config import DEFAULT_API_VERSION, DEFAULT_BASE_URL, RetryConfig
from ._endpoints import ENDPOINTS, Endpoint
from ._exceptions import (
    AgencyZoomError,
    APIConnectionError,
    APIResponseError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    FieldError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from ._sync.client import AgencyZoom
from ._version import __version__

__all__ = [
    "DEFAULT_API_VERSION",
    "DEFAULT_BASE_URL",
    "ENDPOINTS",
    "APIConnectionError",
    "APIResponseError",
    "APIStatusError",
    "APITimeoutError",
    "AgencyZoom",
    "AgencyZoomError",
    "AsyncAgencyZoom",
    "AuthenticationError",
    "BadRequestError",
    "ConfigurationError",
    "ConflictError",
    "Endpoint",
    "FieldError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RetryConfig",
    "UnprocessableEntityError",
    "__version__",
    "models",
]
