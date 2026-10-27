"""Authentication: ``client.auth`` and ``client.v4sso``.

You rarely need these directly: the client logs in and refreshes tokens on its
own. They're exposed for explicit session control and SSO flows.
"""

from __future__ import annotations

from typing import Any, TypeVar

from ..._exceptions import ConfigurationError
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

T = TypeVar("T")


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
        raw = await self._http.auth.authenticate(
            "auth.login", payload, credentials=(payload["username"], payload["password"])
        )
        return self._parse(LoginResponse, raw)

    async def sso_login(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        version: int = LOGIN_API_VERSION,
    ) -> LoginResponse:
        """Log in through V4 SSO. ``POST /auth/ssologin``"""
        payload = self._credentials(username, password, version)
        raw = await self._http.auth.authenticate(
            "auth.sso_login", payload, credentials=(payload["username"], payload["password"])
        )
        return self._parse(LoginResponse, raw)

    async def refresh(self, refresh_token: str | None = None) -> RefreshTokenResponse:
        """Exchange a refresh token for a new access token. ``POST /auth/refresh``"""
        raw = await self._http.auth.refresh(refresh_token)
        return self._parse(RefreshTokenResponse, raw)

    async def logout(self) -> GenericSuccessResponse:
        """Invalidate the current session. ``POST /auth/logout``"""
        raw = await self._http.auth.logout()
        return self._parse(GenericSuccessResponse, raw)

    def _credentials(
        self, username: str | None, password: str | None, version: int
    ) -> dict[str, Any]:
        if (username is None) != (password is None):
            raise ConfigurationError("username and password must be provided together")
        active_username, active_password = self._http.auth.credentials
        fields = {
            "username": username if username is not None else active_username,
            "password": password if password is not None else active_password,
            "version": version,
        }
        return build_body(LoginRequest, None, fields)

    def _parse(self, model: type[T], raw: Any) -> T:
        return parse_response(model, raw, strict=self._http.options.strict_response_validation)


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
        raw = await self._http.auth.authenticate("v4sso.login", payload)
        return parse_response(
            LoginResponse, raw, strict=self._http.options.strict_response_validation
        )
