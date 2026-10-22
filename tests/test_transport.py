"""Retries, backoff, rate limiting, error mapping and caching."""

from __future__ import annotations

import httpx
import pytest
import respx

from agencyzoom import (
    AgencyZoom,
    APIConnectionError,
    APITimeoutError,
    AsyncAgencyZoom,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
    RetryConfig,
)
from agencyzoom._config import RetryConfig as _RetryConfig
from agencyzoom._rate_limit import TokenBucket
from agencyzoom._retry import compute_backoff, parse_retry_after

from .conftest import BASE_URL, make_jwt

EMPLOYEES = "/v1/api/employees"
CREATE_TASK = "/v1/api/tasks"


def test_429_is_retried_honouring_retry_after(
    api: respx.MockRouter, client: AgencyZoom, delays: list[float]
) -> None:
    route = api.get(EMPLOYEES).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json=[{"id": 1, "firstname": "Ann"}]),
        ]
    )
    [employee] = client.settings.employees()
    assert employee.id == 1
    assert route.call_count == 2
    assert delays == [7.0]


def test_429_is_retried_even_for_post(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.post(CREATE_TASK).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"result": True, "id": 9})]
    )
    assert client.tasks.create(title="Call back").id == 9
    assert route.call_count == 2


def test_5xx_retried_for_idempotent_methods(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.get(EMPLOYEES).mock(side_effect=[httpx.Response(503), httpx.Response(200, json=[])])
    client.settings.employees()
    assert route.call_count == 2


def test_5xx_not_retried_for_post(api: respx.MockRouter, client: AgencyZoom) -> None:
    """A POST that failed server-side may have been applied; retrying could duplicate it."""
    route = api.post(CREATE_TASK).mock(return_value=httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(InternalServerError):
        client.tasks.create(title="x")
    assert route.call_count == 1


def test_retries_are_exhausted(api: respx.MockRouter, delays: list[float]) -> None:
    api.get(EMPLOYEES).mock(return_value=httpx.Response(429))
    client = AgencyZoom(
        token=make_jwt(), base_url=BASE_URL, rate_limit_per_minute=None, max_retries=2
    )
    with client, pytest.raises(RateLimitError):
        client.settings.employees()
    assert len(delays) == 2


def test_connection_errors_are_retried_then_raised(
    api: respx.MockRouter, client: AgencyZoom
) -> None:
    route = api.get(EMPLOYEES).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(APIConnectionError):
        client.settings.employees()
    assert route.call_count == 4  # 1 + 3 retries


def test_read_timeout_on_post_is_not_retried(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.post(CREATE_TASK).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(APITimeoutError):
        client.tasks.create(title="x")
    assert route.call_count == 1


def test_error_payload_is_parsed(api: respx.MockRouter, client: AgencyZoom) -> None:
    api.post(CREATE_TASK).mock(
        return_value=httpx.Response(
            400,
            json={
                "error": "Validation failed",
                "fieldErrors": [{"field": "title", "error": "required"}],
            },
        )
    )
    with pytest.raises(BadRequestError) as exc_info:
        client.tasks.create(title="")
    err = exc_info.value
    assert err.message == "Validation failed"
    assert err.field_errors[0].field == "title"
    assert "title: required" in str(err)


def test_404_maps_to_not_found(api: respx.MockRouter, client: AgencyZoom) -> None:
    api.get("/v1/api/tasks/5").mock(return_value=httpx.Response(404, text="Not Found"))
    with pytest.raises(NotFoundError):
        client.tasks.get(5)


def test_reference_data_is_cached(api: respx.MockRouter) -> None:
    route = api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    with AgencyZoom(token=make_jwt(), base_url=BASE_URL, cache_ttl=300) as client:
        client.settings.employees()
        client.settings.employees()
        assert route.call_count == 1
        client.clear_cache()
        client.settings.employees()
    assert route.call_count == 2


def test_cache_disabled_by_default(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
    client.settings.employees()
    client.settings.employees()
    assert route.call_count == 2


def test_default_headers_and_user_agent(api: respx.MockRouter) -> None:
    route = api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
    with AgencyZoom(token=make_jwt(), base_url=BASE_URL, default_headers={"X-Trace": "abc"}) as c:
        c.settings.employees()
    headers = route.calls[0].request.headers
    assert headers["X-Trace"] == "abc"
    assert headers["User-Agent"].startswith("agencyzoom-python-sdk/")


async def test_async_client_retries(api: respx.MockRouter, aclient: AsyncAgencyZoom) -> None:
    route = api.get(EMPLOYEES).mock(side_effect=[httpx.Response(502), httpx.Response(200, json=[])])
    assert await aclient.settings.employees() == []
    assert route.call_count == 2


def test_raw_request_escape_hatch(api: respx.MockRouter, client: AgencyZoom) -> None:
    api.get("/v1/api/brand-new", params={"q": "1"}).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    assert client.request("GET", "/v1/api/brand-new", params={"q": "1"}) == {"ok": True}


# --------------------------------------------------------------------------- pure helpers


def test_token_bucket_allows_burst_then_spaces_requests() -> None:
    now = [0.0]
    bucket = TokenBucket(60, clock=lambda: now[0])  # 1 token/second, burst of 60
    assert all(bucket.reserve() == 0 for _ in range(60))
    assert bucket.reserve() == pytest.approx(1.0)
    assert bucket.reserve() == pytest.approx(2.0)  # queued behind the previous caller
    now[0] = 10.0
    assert bucket.reserve() == 0


def test_parse_retry_after_formats() -> None:
    assert parse_retry_after(httpx.Response(429, headers={"Retry-After": "3"})) == 3.0
    assert parse_retry_after(httpx.Response(429, headers={"Retry-After": "garbage"})) is None
    http_date = parse_retry_after(
        httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
    )
    assert http_date == 0.0  # in the past


def test_backoff_is_bounded_and_jittered() -> None:
    config = _RetryConfig(backoff_factor=1, max_backoff=10)
    for attempt in range(8):
        delay = compute_backoff(config, attempt)
        assert 0 <= delay <= 10
    assert RetryConfig is _RetryConfig
