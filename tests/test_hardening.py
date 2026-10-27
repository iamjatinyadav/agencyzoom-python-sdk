"""Regression tests for credential boundaries, session races and failed exports."""

from __future__ import annotations

import asyncio
import json
from typing import List

import httpx
import pytest
import respx
from pydantic import ValidationError

from agencyzoom import (
    AgencyZoom,
    AgencyZoomError,
    APIResponseError,
    AsyncAgencyZoom,
    ConfigurationError,
    RetryConfig,
)
from agencyzoom._retry import compute_backoff, parse_retry_after
from agencyzoom._tokens import TokenState, jwt_expiry
from agencyzoom._utils import parse_response
from agencyzoom.models import (
    BusinessClassificationResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    Task,
    V4ssoLoginRequest,
)

from .conftest import BASE_URL, make_jwt
from .test_resources import VALID_POLICY

EMPLOYEES = "/v1/api/employees"
LOGIN = "/v1/api/auth/login"
REFRESH = "/v1/api/auth/refresh"


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("operation", ["login", "policy"])
def test_redirects_never_forward_passwords_or_api_tokens(
    api: respx.MockRouter, status: int, operation: str
) -> None:
    target = api.post("https://untrusted.invalid/receive").respond(200, json={"jwt": make_jwt()})
    path = LOGIN if operation == "login" else "/v1/api/policies/create"
    api.post(path).respond(status, headers={"Location": "https://untrusted.invalid/receive"})
    # The SDK must enforce its policy even with an injected client that follows redirects.
    with httpx.Client(follow_redirects=True) as transport, AgencyZoom(
        "alice",
        "fake-password",
        token=make_jwt(),
        api_token="fake-api-token",
        base_url=BASE_URL,
        http_client=transport,
        rate_limit_per_minute=None,
    ) as client:
        call = (
            client.auth.login
            if operation == "login"
            else lambda: client.policies.create(VALID_POLICY)
        )
        with pytest.raises(AgencyZoomError) as exc:
            call()
        assert exc.value.status_code == status
    assert not target.called


async def test_async_redirect_is_not_followed(api: respx.MockRouter) -> None:
    api.post(LOGIN).respond(307, headers={"Location": "https://untrusted.invalid/receive"})
    target = api.post("https://untrusted.invalid/receive").respond(200, json={"jwt": make_jwt()})
    async with httpx.AsyncClient(follow_redirects=True) as transport, AsyncAgencyZoom(
        "alice",
        "fake-password",
        base_url=BASE_URL,
        http_client=transport,
        rate_limit_per_minute=None,
    ) as client:
        with pytest.raises(AgencyZoomError):
            await client.auth.login()
    assert not target.called


def test_explicit_account_switch_updates_renewal_credentials(api: respx.MockRouter) -> None:
    users = []

    def login(request: httpx.Request) -> httpx.Response:
        username = json.loads(request.content)["username"]
        users.append(username)
        return httpx.Response(200, json={"jwt": make_jwt(sub=username)})

    api.post(LOGIN).mock(side_effect=login)
    employees = api.get(EMPLOYEES).mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=[])]
    )
    with AgencyZoom(
        "alice", "fake-password-a", base_url=BASE_URL, rate_limit_per_minute=None
    ) as client:
        client.auth.login("bob", "fake-password-b")
        client.settings.employees()
    assert users == ["bob", "bob"]
    assert employees.call_count == 2


def test_failed_account_switch_preserves_active_identity(api: respx.MockRouter) -> None:
    api.post(LOGIN).respond(401)
    with AgencyZoom("alice", "fake-password", token="alice-token", base_url=BASE_URL) as client:
        with pytest.raises(AgencyZoomError):
            client.auth.login("bob", "wrong-password")
        assert client._http.auth.credentials == ("alice", "fake-password")
        assert client._http.auth.state.access_token == "alice-token"


def test_code_sso_cannot_fall_back_to_previous_account(api: respx.MockRouter) -> None:
    original_login = api.post(LOGIN).respond(200, json={"jwt": "alice-token"})
    api.post("/v1/api/v4sso/sso-login").respond(200, json={"jwt": "bob-token"})
    employees = api.get(EMPLOYEES).respond(401)
    with AgencyZoom("alice", "fake-password", base_url=BASE_URL) as client:
        client.v4sso.login("fake-code")
        with pytest.raises(AgencyZoomError):
            client.settings.employees()
    assert not original_login.called
    assert employees.calls[0].request.headers["Authorization"] == "Bearer bob-token"


@pytest.mark.parametrize(
    "change",
    [
        {"api_version": "v2"},
        {"api_root": "/v2/api"},
        {"endpoint_overrides": {"auth.login": "/v2/api/auth/login"}},
    ],
)
def test_clone_uses_its_own_authentication_route(api: respx.MockRouter, change: dict) -> None:
    login = api.post("/v2/api/auth/login").respond(200, json={"jwt": "new-token"})
    original = api.post(LOGIN).respond(401)
    api.get(EMPLOYEES).respond(200, json=[])
    api.get("/v2/api/employees").respond(200, json=[])
    with AgencyZoom(
        "alice", "fake-password", base_url=BASE_URL, rate_limit_per_minute=None
    ) as client:
        clone = client.with_options(**change)
        clone.settings.employees()
        client.settings.employees()
        assert client._http.auth.state is clone._http.auth.state
    assert login.call_count == 1
    assert not original.called


def test_clone_uses_its_own_refresh_route(api: respx.MockRouter) -> None:
    refresh = api.post("/v2/api/auth/refresh").respond(
        200, json={"jwt": make_jwt(), "refreshToken": "r2"}
    )
    api.get("/v2/api/employees").respond(200, json=[])
    with AgencyZoom(
        token=make_jwt(exp_in=-1), refresh_token="r1", base_url=BASE_URL, rate_limit_per_minute=None
    ) as client:
        client.with_options(api_version="v2").settings.employees()
    assert refresh.call_count == 1


def test_cache_is_isolated_by_host_headers_and_session(api: respx.MockRouter) -> None:
    original = api.get(EMPLOYEES).mock(
        side_effect=[
            httpx.Response(200, json=[{"id": 1}]),
            httpx.Response(200, json=[{"id": 3}]),
            httpx.Response(200, json=[{"id": 4}]),
        ]
    )
    other = api.get("https://other.invalid/v1/api/employees").respond(200, json=[{"id": 2}])
    api.post(LOGIN).respond(200, json={"jwt": "bob-token"})
    with AgencyZoom(
        token="alice-token", base_url=BASE_URL, cache_ttl=300, rate_limit_per_minute=None
    ) as client:
        assert client.settings.employees()[0].id == 1
        assert client.with_options(base_url="https://other.invalid").settings.employees()[0].id == 2
        assert (
            client.with_options(default_headers={"X-Tenant": "different"})
            .settings.employees()[0]
            .id
            == 3
        )
        assert client.settings.employees()[0].id == 1
        client.auth.login("bob", "fake-password")
        assert client.settings.employees()[0].id == 4
        assert client.settings.employees()[0].id == 4
    assert original.call_count == 3
    assert other.call_count == 1


def test_cached_reads_fail_after_close(api: respx.MockRouter) -> None:
    api.get(EMPLOYEES).respond(200, json=[])
    client = AgencyZoom(token="fake-token", base_url=BASE_URL, cache_ttl=300)
    client.settings.employees()
    client.close()
    with pytest.raises(AgencyZoomError, match="closed"):
        client.settings.employees()


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("refresh_mode", ["explicit", "proactive"])
async def test_routine_refresh_preserves_cached_reference_data(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch, mode: str, refresh_mode: str
) -> None:
    employees = api.get(EMPLOYEES).respond(200, json=[{"id": 1}])
    refresh = api.post(REFRESH).respond(200, json={"jwt": "new-token", "refreshToken": "r2"})
    client_type = AgencyZoom if mode == "sync" else AsyncAgencyZoom
    client = client_type(
        token="old-token",
        refresh_token="r1",
        base_url=BASE_URL,
        cache_ttl=300,
        rate_limit_per_minute=None,
    )
    try:
        first = client.settings.employees()
        if mode == "async":
            first = await first
        assert first[0].id == 1
        if refresh_mode == "explicit":
            renewed = client.auth.refresh()
            if mode == "async":
                await renewed
        else:
            monkeypatch.setattr(
                TokenState, "is_expiring", lambda state: state.access_token == "old-token"
            )
        # Copies share both the session and its existing reference-data cache.
        cached = client.with_options(timeout=5).settings.employees()
        if mode == "async":
            cached = await cached
        assert cached[0].id == 1
        assert refresh.call_count == 1
        assert employees.call_count == 1
        assert client._http.auth.state.access_token == "new-token"
    finally:
        if mode == "async":
            await client.close()
        else:
            client.close()


@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_refresh_with_another_token_invalidates_cached_identity(
    api: respx.MockRouter, mode: str
) -> None:
    employees = api.get(EMPLOYEES).mock(
        side_effect=[httpx.Response(200, json=[{"id": 1}]), httpx.Response(200, json=[{"id": 2}])]
    )
    api.post(REFRESH).respond(200, json={"jwt": "bob-token", "refreshToken": "bob-r2"})
    client_type = AgencyZoom if mode == "sync" else AsyncAgencyZoom
    client = client_type(
        token="alice-token",
        refresh_token="alice-r1",
        base_url=BASE_URL,
        cache_ttl=300,
        rate_limit_per_minute=None,
    )
    try:
        first = client.settings.employees()
        if mode == "async":
            first = await first
        assert first[0].id == 1
        refreshed = client.auth.refresh("bob-r1")
        if mode == "async":
            await refreshed
        second = client.settings.employees()
        if mode == "async":
            second = await second
        assert second[0].id == 2
        assert employees.call_count == 2
    finally:
        if mode == "async":
            await client.close()
        else:
            client.close()


def test_token_rejection_invalidates_previously_cached_data(api: respx.MockRouter) -> None:
    employees = api.get(EMPLOYEES).mock(
        side_effect=[httpx.Response(200, json=[{"id": 1}]), httpx.Response(200, json=[{"id": 2}])]
    )
    api.get("/v1/api/tasks/1").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"id": 1})]
    )
    api.post(REFRESH).respond(200, json={"jwt": "new-token", "refreshToken": "r2"})
    with AgencyZoom(
        token="old-token",
        refresh_token="r1",
        base_url=BASE_URL,
        cache_ttl=300,
        rate_limit_per_minute=None,
    ) as client:
        assert client.settings.employees()[0].id == 1
        client.tasks.get(1)
        assert client.settings.employees()[0].id == 2
    assert employees.call_count == 2


def test_fresh_automatic_login_invalidates_cached_reference_data(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    employees = api.get(EMPLOYEES).mock(
        side_effect=[httpx.Response(200, json=[{"id": 1}]), httpx.Response(200, json=[{"id": 2}])]
    )
    login = api.post(LOGIN).respond(200, json={"jwt": "new-token"})
    with AgencyZoom(
        "alice",
        "fake-password",
        token="old-token",
        base_url=BASE_URL,
        cache_ttl=300,
        rate_limit_per_minute=None,
    ) as client:
        assert client.settings.employees()[0].id == 1
        monkeypatch.setattr(
            TokenState, "is_expiring", lambda state: state.access_token == "old-token"
        )
        assert client.settings.employees()[0].id == 2
        assert client.settings.employees()[0].id == 2
    assert login.call_count == 1
    assert employees.call_count == 2


async def test_inflight_pre_refresh_response_does_not_populate_cache(api: respx.MockRouter) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def employees(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer old-token":
            started.set()
            await release.wait()
            return httpx.Response(200, json=[{"id": 1}])
        return httpx.Response(200, json=[{"id": 2}])

    route = api.get(EMPLOYEES).mock(side_effect=employees)
    api.post(REFRESH).respond(200, json={"jwt": "new-token", "refreshToken": "r2"})
    async with AsyncAgencyZoom(
        token="old-token",
        refresh_token="r1",
        base_url=BASE_URL,
        cache_ttl=300,
        rate_limit_per_minute=None,
    ) as client:
        task = asyncio.create_task(client.settings.employees())
        await asyncio.wait_for(started.wait(), 1)
        await client.auth.refresh()
        release.set()
        assert (await task)[0].id == 1
        assert (await client.settings.employees())[0].id == 2
        assert (await client.settings.employees())[0].id == 2
    assert route.call_count == 2


async def test_inflight_old_account_response_does_not_populate_new_cache(
    api: respx.MockRouter,
) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def employees(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer alice-token":
            started.set()
            await release.wait()
            return httpx.Response(200, json=[{"id": 1}])
        return httpx.Response(200, json=[{"id": 2}])

    route = api.get(EMPLOYEES).mock(side_effect=employees)
    api.post(LOGIN).respond(200, json={"jwt": "bob-token"})
    async with AsyncAgencyZoom(
        token="alice-token", base_url=BASE_URL, cache_ttl=300, rate_limit_per_minute=None
    ) as client:
        task = asyncio.create_task(client.settings.employees())
        await asyncio.wait_for(started.wait(), 1)
        await client.auth.login("bob", "fake-password")
        release.set()
        assert (await task)[0].id == 1
        assert (await client.settings.employees())[0].id == 2
        assert (await client.settings.employees())[0].id == 2
    assert route.call_count == 2


async def test_concurrent_public_refreshes_use_rotated_tokens(api: respx.MockRouter) -> None:
    received = []
    active = 0

    async def refresh(request: httpx.Request) -> httpx.Response:
        nonlocal active
        active += 1
        assert active == 1
        received.append(json.loads(request.content)["refreshToken"])
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(
            200,
            json={
                "jwt": make_jwt(sub=str(len(received))),
                "refreshToken": f"refresh-{len(received)}",
            },
        )

    api.post(REFRESH).mock(side_effect=refresh)
    async with AsyncAgencyZoom(
        token=make_jwt(), refresh_token="refresh-0", base_url=BASE_URL, rate_limit_per_minute=None
    ) as client:
        await asyncio.gather(*(client.auth.refresh() for _ in range(5)))
    assert received == [f"refresh-{i}" for i in range(5)]


async def test_logout_waits_for_refresh_and_cannot_be_undone(api: respx.MockRouter) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def refresh(request: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(200, json={"jwt": "renewed-token", "refreshToken": "r2"})

    api.post(REFRESH).mock(side_effect=refresh)
    logout = api.post("/v1/api/auth/logout").respond(200, json={"result": True})
    async with AsyncAgencyZoom(
        token="old-token", refresh_token="r1", base_url=BASE_URL, rate_limit_per_minute=None
    ) as client:
        refreshing = asyncio.create_task(client.auth.refresh())
        await asyncio.wait_for(started.wait(), 1)
        logging_out = asyncio.create_task(client.auth.logout())
        await asyncio.sleep(0)
        assert not logout.called
        release.set()
        await asyncio.gather(refreshing, logging_out)
        assert client._http.auth.state is None
    assert logout.calls[0].request.headers["Authorization"] == "Bearer renewed-token"


async def test_401_does_not_replay_under_a_switched_account(api: respx.MockRouter) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def employees(request: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(401)

    route = api.get(EMPLOYEES).mock(side_effect=employees)
    api.post(LOGIN).respond(200, json={"jwt": "bob-token"})
    async with AsyncAgencyZoom(
        token="alice-token", base_url=BASE_URL, rate_limit_per_minute=None
    ) as client:
        task = asyncio.create_task(client.settings.employees())
        await asyncio.wait_for(started.wait(), 1)
        await client.auth.login("bob", "fake-password")
        release.set()
        with pytest.raises(AgencyZoomError):
            await task
    assert route.call_count == 1


@pytest.mark.parametrize(
    "model",
    [
        TokenState("access-secret", "refresh-secret"),
        LoginRequest(username="alice", password="password-secret"),
        LoginResponse(jwt="access-secret", refreshToken="refresh-secret"),
        RefreshTokenRequest(refreshToken="refresh-secret"),
        RefreshTokenResponse(jwt="access-secret", refreshToken="refresh-secret"),
        V4ssoLoginRequest(code="authorization-code-secret"),
    ],
)
def test_secret_models_hide_credentials_in_repr(model: object) -> None:
    for secret in [
        "access-secret",
        "refresh-secret",
        "password-secret",
        "authorization-code-secret",
    ]:
        assert secret not in repr(model)
        assert secret not in str(model)


def test_business_classification_code_remains_visible() -> None:
    classification = BusinessClassificationResponse(code=541611, description="Consulting")
    assert "code=541611" in repr(classification)
    assert "code=541611" in str(classification)
    assert classification.to_api()["code"] == 541611


def test_secret_headers_and_validation_inputs_are_not_printed() -> None:
    with AgencyZoom(
        token="fake-token",
        default_headers={"Authorization": "access-secret", "X-Api-Token": "api-secret"},
    ) as client:
        assert "access-secret" not in repr(client._http.options)
        assert "api-secret" not in repr(client._http.options)
    with pytest.raises(ValidationError) as exc:
        LoginRequest.model_validate({"password": "password-secret"})
    assert "password-secret" not in str(exc.value)


@pytest.mark.parametrize("alias", ["token", "accessToken", "access_token", "apiToken", "password"])
def test_extra_token_aliases_are_not_printed(alias: str) -> None:
    response = LoginResponse.model_validate({alias: "extra-secret"})
    assert "extra-secret" not in repr(response)
    assert "extra-secret" not in str(response)
    assert response.model_dump()[alias] == "extra-secret"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "5"])
@pytest.mark.parametrize("option", ["timeout", "rate_limit_per_minute", "cache_ttl"])
def test_invalid_numeric_options_are_rejected(option: str, value: object) -> None:
    with pytest.raises(ConfigurationError):
        AgencyZoom(token="fake-token", **{option: value})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_retries": 1.5},
        {"max_retries": float("inf")},
        {"max_retries": float("nan")},
        {"max_retries": "3"},
        {"backoff_factor": float("nan")},
        {"max_backoff": float("inf")},
        {"backoff_factor": True},
        {"retry_statuses": [True]},
        {"retry_statuses": [999]},
        {"respect_retry_after": 1},
    ],
)
def test_invalid_retry_options_fail_at_construction(kwargs: dict) -> None:
    with pytest.raises(ConfigurationError):
        RetryConfig(**kwargs)


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "https://alice:password@host.invalid",
        "https://host.invalid?token=secret",
        "https://host.invalid#fragment",
        "ftp://host.invalid",
    ],
)
def test_base_url_validation_applies_to_constructor_and_copies(url: str) -> None:
    with pytest.raises(ConfigurationError):
        AgencyZoom(token="fake-token", base_url=url)
    with AgencyZoom(token="fake-token") as client, pytest.raises(ConfigurationError):
        client.with_options(base_url=url)


def test_timeout_parts_are_validated() -> None:
    with pytest.raises(ConfigurationError):
        AgencyZoom(token="fake-token", timeout=httpx.Timeout(float("nan")))


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "not-a-date"])
def test_invalid_retry_after_uses_bounded_backoff(value: str) -> None:
    response = httpx.Response(429, headers={"Retry-After": value})
    assert parse_retry_after(response) is None
    assert 0 <= compute_backoff(RetryConfig(), 10000, response) <= 30


def test_overflowing_token_expiry_is_ignored() -> None:
    assert (
        TokenState.from_auth_response({"jwt": "fake-token", "expiresIn": 10**1000}).expires_at
        is None
    )
    assert jwt_expiry("invalid.jwt.data") is None


def test_raw_response_fallback_preserves_every_original_value() -> None:
    raw = [{"id": "bad-value"}, 123]
    result = parse_response(List[Task], raw)
    assert result == raw == [{"id": "bad-value"}, 123]


def test_strict_response_validation_can_be_enabled_per_copy(api: respx.MockRouter) -> None:
    api.get("/v1/api/tasks/1").respond(200, json={"id": "invalid"})
    with AgencyZoom(token="fake-token", base_url=BASE_URL) as client:
        assert client.tasks.get(1).id is None
        with pytest.raises(APIResponseError) as exc:
            client.with_options(strict_response_validation=True).tasks.get(1)
        assert exc.value.body == {"id": "invalid"}


@pytest.mark.parametrize(
    "payload",
    [
        {"totalCount": 2, "tasks": []},
        {"totalCount": "bad", "tasks": []},
        {"totalCount": True, "tasks": []},
        {"totalCount": -1, "tasks": []},
        {"tasks": [123]},
    ],
)
def test_incomplete_or_invalid_pagination_raises(
    api: respx.MockRouter, client: AgencyZoom, payload: dict
) -> None:
    api.post("/v1/api/tasks/list").respond(200, json=payload)
    with pytest.raises(APIResponseError):
        list(client.tasks.paginate())


def test_pagination_empty_result_is_valid(api: respx.MockRouter, client: AgencyZoom) -> None:
    api.post("/v1/api/tasks/list").respond(200, json={"totalCount": 0, "tasks": []})
    assert list(client.tasks.paginate()) == []


def test_pagination_follows_total_when_server_caps_page_size(
    api: respx.MockRouter, client: AgencyZoom
) -> None:
    route = api.post("/v1/api/tasks/list").mock(
        side_effect=[
            httpx.Response(200, json={"totalCount": 3, "tasks": [{"id": 1}, {"id": 2}]}),
            httpx.Response(200, json={"totalCount": 3, "tasks": [{"id": 3}]}),
        ]
    )
    assert [item.id for item in client.tasks.paginate(page_size=100)] == [1, 2, 3]
    assert route.call_count == 2


def test_pagination_safety_limit_raises(
    api: respx.MockRouter, client: AgencyZoom, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agencyzoom._sync._resource.MAX_PAGES", 1)
    api.post("/v1/api/tasks/list").respond(200, json={"tasks": [{"id": 1}]})
    with pytest.raises(APIResponseError, match="safety limit"):
        list(client.tasks.paginate(page_size=1))
