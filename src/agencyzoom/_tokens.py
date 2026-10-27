"""Access-token bookkeeping (pure data, no I/O)."""

from __future__ import annotations

import base64
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any

from ._exceptions import APIResponseError

__all__ = ["TokenState", "jwt_expiry"]

#: Refresh this many seconds before the token actually expires.
EXPIRY_LEEWAY = 60.0


def jwt_expiry(token: str) -> float | None:
    """Read the ``exp`` claim from a JWT without verifying it (that's the server's job)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return _finite_float(claims.get("exp")) if isinstance(claims, dict) else None
    except (IndexError, ValueError, TypeError, AttributeError):
        return None


def _finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class TokenState:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: float | None = None
    """Unix timestamp; ``None`` when unknown (the token is then used until a 401)."""

    @classmethod
    def from_token(cls, access_token: str, refresh_token: str | None = None) -> TokenState:
        return cls(access_token, refresh_token, jwt_expiry(access_token))

    @classmethod
    def from_auth_response(cls, data: Any, previous: TokenState | None = None) -> TokenState:
        if not isinstance(data, dict):
            raise APIResponseError("Authentication response was not a JSON object", body=data)
        access = data.get("jwt") or data.get("token") or data.get("accessToken")
        if not access or not isinstance(access, str):
            message = data.get("error") or data.get("message") or "no token in response"
            raise APIResponseError(f"Authentication failed: {message}", body=data)

        refresh = data.get("refreshToken") or (previous.refresh_token if previous else None)
        expires_in = _finite_float(data.get("expiresIn"))
        if expires_in is not None and expires_in > 0:
            expires_at: float | None = time.time() + expires_in
        else:
            expires_at = jwt_expiry(access)
        return cls(access, refresh if isinstance(refresh, str) else None, expires_at)

    def is_expiring(self, leeway: float = EXPIRY_LEEWAY) -> bool:
        return self.expires_at is not None and time.time() >= self.expires_at - leeway
