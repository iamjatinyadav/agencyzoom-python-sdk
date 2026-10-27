from __future__ import annotations

import base64
import json
import time
from collections.abc import AsyncIterator, Iterator

import pytest
import respx

from agencyzoom import AgencyZoom, AsyncAgencyZoom

BASE_URL = "https://api.test.agencyzoom.local"


def make_jwt(exp_in: float = 3600, sub: str = "user") -> str:
    """An unsigned JWT with an ``exp`` claim; the SDK only reads it."""

    def b64(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, 'exp': time.time() + exp_in})}.sig"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AGENCYZOOM_USERNAME",
        "AGENCYZOOM_PASSWORD",
        "AGENCYZOOM_TOKEN",
        "AGENCYZOOM_API_TOKEN",
        "AGENCYZOOM_BASE_URL",
        "AGENCYZOOM_API_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Make retries/backoff instant while recording the requested delays."""
    delays: list[float] = []

    def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("agencyzoom._sync._http.sleep", fake_sleep)
    monkeypatch.setattr("agencyzoom._async._http.sleep", fake_async_sleep)
    return delays


@pytest.fixture
def delays(_no_sleep: list[float]) -> list[float]:
    return _no_sleep


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client() -> Iterator[AgencyZoom]:
    with AgencyZoom(token=make_jwt(), base_url=BASE_URL, rate_limit_per_minute=None) as c:
        yield c


@pytest.fixture
async def aclient() -> AsyncIterator[AsyncAgencyZoom]:
    async with AsyncAgencyZoom(
        token=make_jwt(), base_url=BASE_URL, rate_limit_per_minute=None
    ) as c:
        yield c
