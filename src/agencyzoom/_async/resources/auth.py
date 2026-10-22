"""Authentication: ``client.auth`` and ``client.v4sso``.

You rarely need these directly: the client logs in and refreshes tokens on its
own. They're exposed for explicit session control and SSO flows.
"""

from __future__ import annotations

from typing import Any

from ..._exceptions import ConfigurationError
from ..._tokens import TokenState
from ..._utils import build_body, parse_response
from ...models import (
    GenericSuccessResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenResponse,
    V4ssoAuthResponse,
    V4ssoLoginRequest,
)
from .._auth import LOGIN_API_VERSION
from .._resource import AsyncAPIResource

__all__ = ["AsyncAuth", "AsyncV4SSO"]


class AsyncAuth(AsyncAPIResource):
    """Explicit session management. Successful calls update the client's token."""

    async def login(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        version: int = LOGIN_API_VERSION,
    ) -> LoginResponse:
        """Log in (defaults to the client's credentials). ``POST /auth/login``"""
        payload = self._credentials(username, password, version)
        raw = await self._call("auth.login", body=payload, authenticated=False)
        return self._store_session(raw)

    async def sso_login(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        version: int = LOGIN_API_VERSION,
    ) -> LoginResponse:
        """Log in through V4 SSO. ``POST /auth/ssologin``"""
        payload = self._credentials(username, password, version)
        raw = await self._call("auth.sso_login", body=payload, authenticated=False)
        return self._store_session(raw)

    async def refresh(self, refresh_token: str | None = None) -> RefreshTokenResponse:
        """Exchange a refresh token for a new access token. ``POST /auth/refresh``"""
        current = self._http.auth.state
        token = refresh_token or (current.refresh_token if current else None)
        if not token:
            raise ConfigurationError("No refresh token available; log in with version=2 first.")
        raw = await self._call("auth.refresh", body={"refreshToken": token}, authenticated=False)
        self._http.auth.set_state(TokenState.from_auth_response(raw, previous=current))
        return parse_response(RefreshTokenResponse, raw)

    async def logout(self) -> GenericSuccessResponse:
        """Invalidate the current session. ``POST /auth/logout``"""
        result = await self._call("auth.logout", cast_to=GenericSuccessResponse)
        self._http.auth.set_state(None)
        return result

    def _credentials(
        self, username: str | None, password: str | None, version: int
    ) -> dict[str, Any]:
        options = self._http.options
        fields = {
            "username": username or options.username,
            "password": password or options.password,
            "version": version,
        }
        return build_body(LoginRequest, None, fields)

    def _store_session(self, raw: Any) -> LoginResponse:
        self._http.auth.set_state(TokenState.from_auth_response(raw))
        return parse_response(LoginResponse, raw)


class AsyncV4SSO(AsyncAPIResource):
    """Vertafore V4 single sign-on."""

    async def get_auth_params(self) -> V4ssoAuthResponse:
        """Get the URL to start the SSO flow. ``POST /v4sso/get-auth-params``"""
        return await self._call(
            "v4sso.get_auth_params", cast_to=V4ssoAuthResponse, authenticated=False
        )

    async def login(self, code: str, *, version: int | None = LOGIN_API_VERSION) -> LoginResponse:
        """Complete the SSO flow with the authorization ``code``. ``POST /v4sso/sso-login``"""
        fields: dict[str, Any] = {"code": code}
        if version is not None:
            fields["version"] = version
        payload = build_body(V4ssoLoginRequest, None, fields)
        raw = await self._call("v4sso.login", body=payload, authenticated=False)
        self._http.auth.set_state(TokenState.from_auth_response(raw))
        return parse_response(LoginResponse, raw)
