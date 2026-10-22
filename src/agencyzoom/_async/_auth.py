"""Login, proactive refresh, and recovery from expired tokens."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Mapping

from .._config import ClientOptions
from .._exceptions import APIStatusError, ConfigurationError
from .._tokens import TokenState
from ._compat import Lock

__all__ = ["AsyncTokenManager"]

logger = logging.getLogger("agencyzoom")

LOGIN_ENDPOINT = "auth.login"
REFRESH_ENDPOINT = "auth.refresh"
#: Ask the login endpoint for refresh tokens and expiry information.
LOGIN_API_VERSION = 2

#: (endpoint_id, json_body) -> decoded response, sent without authentication.
SendJSON = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


class AsyncTokenManager:
    """Owns the bearer token for a client.

    * With ``username``/``password`` it logs in lazily on the first request.
    * Tokens are refreshed shortly *before* they expire, using the refresh token,
      falling back to a fresh login if the refresh is rejected.
    * A lock guarantees that concurrent requests trigger a single refresh.
    """

    def __init__(self, options: ClientOptions, send_json: SendJSON) -> None:
        self._options = options
        self._send_json = send_json
        self._lock = Lock()
        self._state: TokenState | None = (
            TokenState.from_token(options.token, options.refresh_token) if options.token else None
        )

    @property
    def state(self) -> TokenState | None:
        return self._state

    @property
    def can_reauthenticate(self) -> bool:
        has_refresh = self._state is not None and self._state.refresh_token is not None
        return has_refresh or self._has_credentials

    @property
    def _has_credentials(self) -> bool:
        return bool(self._options.username and self._options.password)

    def set_state(self, state: TokenState | None) -> None:
        self._state = state

    async def get_token(self) -> str:
        state = self._state
        if state is not None and not state.is_expiring():
            return state.access_token
        async with self._lock:
            state = self._state  # another task may have refreshed while we waited
            if state is None or (state.is_expiring() and self.can_reauthenticate):
                state = await self._renew(state)
            return state.access_token

    async def handle_unauthorized(self, rejected_token: str) -> bool:
        """Called after a 401. Returns ``True`` if a new token is available to retry with."""
        async with self._lock:
            state = self._state
            if state is not None and state.access_token != rejected_token:
                return True  # already renewed by a concurrent request
            if not self.can_reauthenticate:
                return False
            await self._renew(state)
            return True

    async def login(self) -> TokenState:
        if not self._has_credentials:
            raise ConfigurationError("Cannot log in: no username/password configured.")
        logger.debug("Logging in to AgencyZoom as %s", self._options.username)
        data = await self._send_json(
            LOGIN_ENDPOINT,
            {
                "username": self._options.username,
                "password": self._options.password,
                "version": LOGIN_API_VERSION,
            },
        )
        self._state = TokenState.from_auth_response(data)
        return self._state

    async def refresh(self) -> TokenState:
        state = self._state
        if state is None or state.refresh_token is None:
            raise ConfigurationError("Cannot refresh: no refresh token available.")
        logger.debug("Refreshing AgencyZoom access token")
        data = await self._send_json(REFRESH_ENDPOINT, {"refreshToken": state.refresh_token})
        self._state = TokenState.from_auth_response(data, previous=state)
        return self._state

    async def _renew(self, state: TokenState | None) -> TokenState:
        if state is not None and state.refresh_token:
            try:
                return await self.refresh()
            except APIStatusError as exc:
                if not self._has_credentials:
                    raise
                logger.info("Token refresh failed (%s); logging in again", exc)
        if self._has_credentials:
            return await self.login()
        if state is None:
            raise ConfigurationError("No AgencyZoom credentials available.")
        return state  # static token: nothing else we can do; let the API decide
