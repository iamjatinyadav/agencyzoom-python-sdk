"""Synchronized session ownership and authentication through the current API routes."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Mapping, Optional

from .._config import ClientOptions
from .._exceptions import APIStatusError, ConfigurationError
from .._tokens import TokenState
from ._compat import Lock

__all__ = ["AsyncTokenManager"]

logger = logging.getLogger("agencyzoom")
LOGIN_ENDPOINT = "auth.login"
REFRESH_ENDPOINT = "auth.refresh"
LOGIN_API_VERSION = 2
SendJSON = Callable[[str, Optional[Mapping[str, Any]], Optional[str]], Awaitable[Any]]


class _Session:
    """Shared state; every mutation is performed under the same lock."""

    def __init__(self, options: ClientOptions) -> None:
        self.lock = Lock()
        self.username = options.username
        self.password = options.password
        self.login_endpoint = LOGIN_ENDPOINT
        self.state = (
            TokenState.from_token(options.token, options.refresh_token) if options.token else None
        )
        self.revision = 0
        self.cache_revision = 0
        self.identity = 0


class AsyncTokenManager:
    """A view of one shared session, authenticated through this client's routes.

    Explicit and automatic login, refresh and logout use the same lock. Copies
    share state while keeping their own sender, so routing overrides apply to
    authentication as well as resource requests.
    """

    def __init__(self, options: ClientOptions, send_json: SendJSON) -> None:
        self._session = _Session(options)
        self._send_json = send_json

    def copy(self, send_json: SendJSON) -> AsyncTokenManager:
        clone = object.__new__(type(self))
        clone._session = self._session
        clone._send_json = send_json
        return clone

    @property
    def state(self) -> TokenState | None:
        return self._session.state

    @property
    def revision(self) -> int:
        return self._session.revision

    @property
    def cache_revision(self) -> int:
        return self._session.cache_revision

    @property
    def identity(self) -> int:
        return self._session.identity

    @property
    def credentials(self) -> tuple[str | None, str | None]:
        return self._session.username, self._session.password

    @property
    def can_reauthenticate(self) -> bool:
        return bool((self.state and self.state.refresh_token) or self._has_credentials)

    @property
    def _has_credentials(self) -> bool:
        return bool(self._session.username and self._session.password)

    def _store(
        self,
        state: TokenState | None,
        *,
        new_identity: bool = False,
        invalidate_cache: bool = False,
    ) -> None:
        self._session.state = state
        self._session.revision += 1
        if new_identity:
            self._session.identity += 1
        if new_identity or invalidate_cache:
            self._session.cache_revision += 1

    async def get_token(self) -> str:
        state = self.state
        if state is not None and not state.is_expiring():
            return state.access_token
        async with self._session.lock:
            state = self.state
            if state is None or (state.is_expiring() and self.can_reauthenticate):
                await self._renew(state)
                state = self.state
            assert state is not None
            return state.access_token

    async def handle_unauthorized(self, rejected_token: str, identity: int) -> bool:
        async with self._session.lock:
            # Never replay a request under a different explicitly selected account.
            if identity != self.identity:
                return False
            state = self.state
            if state is not None and state.access_token != rejected_token:
                return True
            # An actual token rejection may reflect changed permissions. Unlike
            # routine renewal, invalidate reference data before recovering.
            self._session.cache_revision += 1
            if not self.can_reauthenticate:
                return False
            await self._renew(state)
            return True

    async def authenticate(
        self,
        endpoint_id: str,
        body: Mapping[str, Any],
        *,
        credentials: tuple[str, str] | None = None,
    ) -> Any:
        async with self._session.lock:
            raw = await self._send_json(endpoint_id, body, None)
            state = TokenState.from_auth_response(raw)
            # Commit credentials only after successful authentication. Code-based
            # SSO must not fall back to credentials from a previous identity.
            self._session.username, self._session.password = credentials or (None, None)
            self._session.login_endpoint = endpoint_id
            self._store(state, new_identity=True)
            return raw

    async def refresh(self, refresh_token: str | None = None) -> Any:
        async with self._session.lock:
            state = self.state
            token = (
                refresh_token
                if refresh_token is not None
                else (state.refresh_token if state else None)
            )
            if not token:
                raise ConfigurationError("No refresh token available; log in with version=2 first.")
            changing_identity = refresh_token is not None and (
                state is None or token != state.refresh_token
            )
            raw = await self._send_json(REFRESH_ENDPOINT, {"refreshToken": token}, None)
            renewed = TokenState.from_auth_response(
                raw, previous=None if changing_identity else state
            )
            if changing_identity:
                self._session.username = self._session.password = None
            self._store(renewed, new_identity=changing_identity)
            return raw

    async def logout(self) -> Any:
        async with self._session.lock:
            state = self.state
            if state is None or (state.is_expiring() and self.can_reauthenticate):
                await self._renew(state)
                state = self.state
            assert state is not None
            raw = await self._send_json("auth.logout", None, state.access_token)
            self._store(None, new_identity=True)
            return raw

    async def _login(self) -> None:
        if not self._has_credentials:
            raise ConfigurationError("Cannot log in: no username/password configured.")
        raw = await self._send_json(
            self._session.login_endpoint,
            {
                "username": self._session.username,
                "password": self._session.password,
                "version": LOGIN_API_VERSION,
            },
            None,
        )
        self._store(TokenState.from_auth_response(raw), invalidate_cache=True)

    async def _renew(self, state: TokenState | None) -> None:
        if state is not None and state.refresh_token:
            try:
                raw = await self._send_json(
                    REFRESH_ENDPOINT, {"refreshToken": state.refresh_token}, None
                )
                self._store(TokenState.from_auth_response(raw, previous=state))
                return
            except APIStatusError as exc:
                if not self._has_credentials or exc.status_code not in {400, 401, 403}:
                    raise
                logger.info("Token refresh rejected (%d); logging in again", exc.status_code)
        if self._has_credentials:
            await self._login()
        elif state is None:
            raise ConfigurationError("No AgencyZoom credentials available.")
