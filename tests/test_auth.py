from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from agencyzoom import AgencyZoom, AsyncAgencyZoom, AuthenticationError, ConfigurationError

from .conftest import BASE_URL, make_jwt

LOGIN = "/v1/api/auth/login"
REFRESH = "/v1/api/auth/refresh"
EMPLOYEES = "/v1/api/employees"


def login_ok(token: str, refresh: str = "refresh-1", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(
        200, json={"jwt": token, "refreshToken": refresh, "expiresIn": expires_in}
    )


def test_requires_credentials() -> None:
    with pytest.raises(ConfigurationError):
        AgencyZoom()


def test_username_without_password_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        AgencyZoom(username="a@b.c")


def test_credentials_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENCYZOOM_TOKEN", make_jwt())
    AgencyZoom().close()


def test_lazy_login_then_token_reuse(api: respx.MockRouter) -> None:
    token = make_jwt()
    login = api.post(LOGIN).mock(return_value=login_ok(token))
    employees = api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))

    with AgencyZoom("owner@agency.com", "pw", base_url=BASE_URL) as client:
        assert login.call_count == 0  # nothing happens until the first API call
        client.settings.employees()
        client.settings.employees()

    assert login.call_count == 1
    sent = json.loads(login.calls[0].request.content)
    assert sent == {"username": "owner@agency.com", "password": "pw", "version": 2}
    assert employees.calls[0].request.headers["Authorization"] == f"Bearer {token}"
    assert "Authorization" not in login.calls[0].request.headers


def test_401_triggers_refresh_and_retry(api: respx.MockRouter) -> None:
    old, new = make_jwt(sub="old"), make_jwt(sub="new")
    api.post(LOGIN).mock(return_value=login_ok(old))
    refresh = api.post(REFRESH).mock(return_value=login_ok(new, refresh="refresh-2"))
    employees = api.get(EMPLOYEES).mock(
        side_effect=[httpx.Response(401, json={"error": "expired"}), httpx.Response(200, json=[])]
    )

    with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client:
        assert client.settings.employees() == []

    assert json.loads(refresh.calls[0].request.content) == {"refreshToken": "refresh-1"}
    assert employees.calls[1].request.headers["Authorization"] == f"Bearer {new}"


def test_expiring_token_is_refreshed_proactively(api: respx.MockRouter) -> None:
    api.post(LOGIN).mock(return_value=login_ok(make_jwt(), expires_in=5))  # inside leeway
    new = make_jwt(sub="new")
    refresh = api.post(REFRESH).mock(return_value=login_ok(new))
    employees = api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))

    with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client:
        client.auth.login()
        client.settings.employees()

    assert refresh.call_count == 1
    assert employees.calls[0].request.headers["Authorization"] == f"Bearer {new}"


def test_failed_refresh_falls_back_to_login(api: respx.MockRouter) -> None:
    first, second = make_jwt(sub="1"), make_jwt(sub="2")
    login = api.post(LOGIN).mock(side_effect=[login_ok(first), login_ok(second)])
    api.post(REFRESH).mock(return_value=httpx.Response(401, json={"error": "bad refresh"}))
    api.get(EMPLOYEES).mock(side_effect=[httpx.Response(401), httpx.Response(200, json=[])])

    with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client:
        client.settings.employees()

    assert login.call_count == 2


def test_static_token_401_raises(api: respx.MockRouter, client: AgencyZoom) -> None:
    api.get(EMPLOYEES).mock(return_value=httpx.Response(401, json={"error": "Invalid token"}))
    with pytest.raises(AuthenticationError, match="Invalid token") as exc_info:
        client.settings.employees()
    assert exc_info.value.status_code == 401


def test_logout_clears_session(api: respx.MockRouter) -> None:
    api.post(LOGIN).mock(return_value=login_ok(make_jwt()))
    api.post("/v1/api/auth/logout").mock(return_value=httpx.Response(200, json={"result": True}))
    with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client:
        client.auth.login()
        assert client.auth.logout().result is True
        assert client._http.auth.state is None


async def test_concurrent_requests_share_one_login(api: respx.MockRouter) -> None:
    login = api.post(LOGIN).mock(return_value=login_ok(make_jwt()))
    api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))

    async with AsyncAgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client:
        await asyncio.gather(*(client.settings.employees() for _ in range(10)))

    assert login.call_count == 1


def test_secrets_never_appear_in_repr() -> None:
    with AgencyZoom("u@x.com", "hunter2", api_token="tok-secret", base_url=BASE_URL) as client:
        text = repr(client._http.options) + repr(client)
    assert "hunter2" not in text
    assert "tok-secret" not in text
