"""Edge cases: versioning, configuration, malformed data, lifecycle and concurrency."""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import respx

from agencyzoom import (
    AgencyZoom,
    AgencyZoomError,
    APIResponseError,
    AsyncAgencyZoom,
    ConfigurationError,
    InternalServerError,
)

from .conftest import BASE_URL, make_jwt

EMPLOYEES = "/v1/api/employees"


def new_client(**kwargs: object) -> AgencyZoom:
    options: dict[str, object] = {
        "token": make_jwt(),
        "base_url": BASE_URL,
        "rate_limit_per_minute": None,
    }
    options.update(kwargs)
    return AgencyZoom(**options)  # type: ignore[arg-type]


def sent_json(route: respx.Route, index: int = 0) -> object:
    return json.loads(route.calls[index].request.content)


# --------------------------------------------------------------------------- API versioning


class TestVersioning:
    def test_api_version_moves_every_endpoint(self, api: respx.MockRouter) -> None:
        route = api.post("/v2/api/leads/list").mock(return_value=httpx.Response(200, json={}))
        with new_client(api_version="v2") as client:
            client.leads.search()
        assert route.called

    def test_api_version_from_environment(
        self, api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENCYZOOM_API_VERSION", "v3")
        route = api.get("/v3/api/employees").mock(return_value=httpx.Response(200, json=[]))
        with new_client() as client:
            client.settings.employees()
        assert route.called

    def test_api_root_replaces_the_prefix(self, api: respx.MockRouter) -> None:
        route = api.get("/api/v2/leads/7").mock(return_value=httpx.Response(200, json={"id": 7}))
        with new_client(api_root="/api/v2/") as client:
            assert client.leads.get(7).id == 7
        assert route.called

    def test_empty_api_root(self, api: respx.MockRouter) -> None:
        route = api.get("/employees").mock(return_value=httpx.Response(200, json=[]))
        with new_client(api_root="") as client:
            client.settings.employees()
        assert route.called

    def test_override_path_only_keeps_method(self, api: respx.MockRouter) -> None:
        route = api.get("/v2/api/leads/9/detail").mock(
            return_value=httpx.Response(200, json={"id": 9})
        )
        with new_client(endpoint_overrides={"leads.get": "/v2/api/leads/{lead_id}/detail"}) as c:
            c.leads.get(9)
        assert route.called

    def test_override_method_and_path(self, api: respx.MockRouter) -> None:
        route = api.get("/v2/api/leads/search").mock(return_value=httpx.Response(200, json={}))
        unchanged = api.get("/v1/api/employees").mock(return_value=httpx.Response(200, json=[]))
        with new_client(endpoint_overrides={"leads.search": "get /v2/api/leads/search"}) as c:
            c.leads.search()
            c.settings.employees()  # other endpoints are untouched
        assert route.called
        assert unchanged.called

    def test_overrides_apply_to_login_too(self, api: respx.MockRouter) -> None:
        login = api.post("/v2/api/auth/login").mock(
            return_value=httpx.Response(200, json={"jwt": make_jwt()})
        )
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
        with AgencyZoom(
            "u@x.com",
            "pw",
            base_url=BASE_URL,
            endpoint_overrides={"auth.login": "/v2/api/auth/login"},
        ) as client:
            client.settings.employees()
        assert login.called

    def test_unknown_override_suggests_the_right_id(self) -> None:
        with pytest.raises(ConfigurationError, match=r"Did you mean 'leads\.search'"):
            new_client(endpoint_overrides={"lead.search": "/v2/api/leads/list"})

    @pytest.mark.parametrize(
        "override",
        ["v2/api/leads/{lead_id}", "/v2/api/leads/{id}", "/v2/api/leads", "DELETE v2/leads"],
    )
    def test_invalid_overrides_fail_fast(self, override: str) -> None:
        with pytest.raises(ConfigurationError):
            new_client(endpoint_overrides={"leads.get": override})

    @pytest.mark.parametrize("version", ["v 2", "../v1", "", "  "])
    def test_invalid_api_version(self, version: str) -> None:
        if not version.strip():
            new_client(api_version=version).close()  # blank -> default
            return
        with pytest.raises(ConfigurationError):
            new_client(api_version=version)

    def test_with_options_scopes_changes_and_shares_the_session(
        self, api: respx.MockRouter
    ) -> None:
        login = api.post("/v2/api/auth/login").mock(
            return_value=httpx.Response(200, json={"jwt": make_jwt()})
        )
        v1 = api.get("/v1/api/employees").mock(return_value=httpx.Response(200, json=[]))
        v2 = api.get("/v2/api/employees").mock(return_value=httpx.Response(200, json=[]))
        with AgencyZoom("u@x.com", "pw", base_url=BASE_URL, default_headers={"A": "1"}) as client:
            beta = client.with_options(api_version="v2", default_headers={"B": "2"}, timeout=5)
            beta.settings.employees()
            client.settings.employees()
        assert login.call_count == 1  # one session for both
        assert v1.called
        assert v2.called
        headers = v2.calls[0].request.headers
        assert headers["A"] == "1"
        assert headers["B"] == "2"
        assert "B" not in v1.calls[0].request.headers

    def test_with_options_validates_overrides(self, client: AgencyZoom) -> None:
        with pytest.raises(ConfigurationError):
            client.with_options(endpoint_overrides={"nope": "/x"})

    def test_raw_request_for_unlisted_endpoints(
        self, api: respx.MockRouter, client: AgencyZoom
    ) -> None:
        api.post("/v2/api/brand-new").mock(return_value=httpx.Response(200, json={"ok": 1}))
        assert client.request("post", "v2/api/brand-new", json={}) == {"ok": 1}


# --------------------------------------------------------------------------- configuration


class TestConfiguration:
    @pytest.mark.parametrize("url", ["api.agencyzoom.com", "ftp://x", "  "])
    def test_bad_base_url(self, url: str) -> None:
        if not url.strip():
            new_client(base_url=url).close()  # blank -> default
            return
        with pytest.raises(ConfigurationError, match="base_url"):
            new_client(base_url=url)

    def test_base_url_with_path_prefix(self, api: respx.MockRouter) -> None:
        route = api.get("/proxy/az/v1/api/employees").mock(
            return_value=httpx.Response(200, json=[])
        )
        with new_client(base_url=f"{BASE_URL}/proxy/az/") as client:
            client.settings.employees()
        assert route.called

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"timeout": -1},
            {"timeout": 0},
            {"rate_limit_per_minute": 0},
            {"cache_ttl": -5},
            {"max_retries": -1},
            {"max_retries": True},
        ],
    )
    def test_invalid_numbers(self, kwargs: dict[str, object]) -> None:
        with pytest.raises(ConfigurationError):
            new_client(**kwargs)

    def test_blank_env_vars_count_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENCYZOOM_TOKEN", "   ")
        with pytest.raises(ConfigurationError, match="credentials"):
            AgencyZoom()


# --------------------------------------------------------------------------- path parameters


class TestPathParameters:
    @pytest.mark.parametrize("bad", [None, True, False, "", "   "])
    def test_invalid_ids_are_rejected_before_sending(
        self, api: respx.MockRouter, client: AgencyZoom, bad: object
    ) -> None:
        with pytest.raises(ValueError, match="lead_id"):
            client.leads.get(bad)  # type: ignore[arg-type]
        assert not api.calls

    @pytest.mark.parametrize("value", ["a/b c", ".", "..", "1/../2", -1, 1.5, "-1", "1.0"])
    def test_non_numeric_ids_are_rejected(
        self, api: respx.MockRouter, client: AgencyZoom, value: object
    ) -> None:
        with pytest.raises(ValueError, match="lead_id"):
            client.leads.get(value)  # type: ignore[arg-type]
        assert not api.calls

    def test_string_and_int_ids(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.get("/v1/api/tasks/42").mock(return_value=httpx.Response(200, json={"id": 42}))
        client.tasks.get(42)
        client.tasks.get(" 42 ")  # type: ignore[arg-type]
        assert route.call_count == 2


# --------------------------------------------------------------------------- odd responses


class TestResponses:
    def test_html_with_200_raises_a_clear_error(
        self, api: respx.MockRouter, client: AgencyZoom
    ) -> None:
        api.get(EMPLOYEES).mock(
            return_value=httpx.Response(
                200, text="<html>Down for maintenance</html>", headers={"content-type": "text/html"}
            )
        )
        with pytest.raises(APIResponseError, match="maintenance"):
            client.settings.employees()

    @pytest.mark.parametrize("response", [httpx.Response(204), httpx.Response(200, text="  ")])
    def test_empty_bodies(
        self, api: respx.MockRouter, client: AgencyZoom, response: httpx.Response
    ) -> None:
        api.delete("/v1/api/tasks/1").mock(return_value=response)
        assert client.tasks.delete(1) is None

    def test_null_list(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=None))
        assert client.settings.employees() is None

    def test_html_error_page(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        api.post("/v1/api/tasks").mock(
            return_value=httpx.Response(502, text="<h1>Bad Gateway</h1>")
        )
        with pytest.raises(InternalServerError, match="Bad Gateway") as exc:
            client.tasks.create(title="x")
        assert exc.value.status_code == 502

    def test_json_error_that_is_not_an_object(
        self, api: respx.MockRouter, client: AgencyZoom
    ) -> None:
        api.post("/v1/api/tasks").mock(return_value=httpx.Response(400, json=["nope"]))
        with pytest.raises(AgencyZoomError, match="400"):
            client.tasks.create(title="x")

    def test_unexpected_shape_falls_back_to_raw(
        self, api: respx.MockRouter, client: AgencyZoom
    ) -> None:
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json={"data": [{"id": 1}]}))
        assert client.settings.employees() == {"data": [{"id": 1}]}  # type: ignore[comparison-overlap]

    @pytest.mark.parametrize(
        "payload", [{}, {"jwt": ""}, {"error": "Invalid user name"}, ["jwt"], "token"]
    )
    def test_login_without_token(self, api: respx.MockRouter, payload: object) -> None:
        api.post("/v1/api/auth/login").mock(return_value=httpx.Response(200, json=payload))
        with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client, pytest.raises(
            APIResponseError
        ):
            client.settings.employees()

    @pytest.mark.parametrize("expires_in", ["3600", "garbage", None, -10, 0, "inf"])
    def test_odd_expires_in_values(self, api: respx.MockRouter, expires_in: object) -> None:
        api.post("/v1/api/auth/login").mock(
            return_value=httpx.Response(200, json={"jwt": make_jwt(), "expiresIn": expires_in})
        )
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
        with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client:
            assert client.settings.employees() == []

    def test_many_bad_fields_across_many_items_are_all_repaired(
        self, api: respx.MockRouter, client: AgencyZoom, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Regression: a real response had 4 off-spec fields on every item.

        Earlier the parser fixed one field per pass and gave up after 5 passes,
        returning a raw dict instead of the typed model.
        """
        tasks = [
            {"id": i, "status": "open", "duration": "1h", "completedBy": "Ann", "customerId": "x"}
            for i in range(25)
        ]
        api.post("/v1/api/tasks/list").mock(
            return_value=httpx.Response(200, json={"totalCount": 25, "tasks": tasks})
        )
        with caplog.at_level(logging.WARNING, logger="agencyzoom"):
            result = client.tasks.search()
        assert [t.id for t in result.tasks or []] == list(range(25))
        assert result.tasks[0].status is None  # type: ignore[index]
        warnings = [r.getMessage() for r in caplog.records]
        assert len(warnings) == 1, warnings  # one concise warning, not one per field
        for field in ("status", "duration", "completedBy", "customerId"):
            assert warnings[0].count(f"tasks[].{field} (int_parsing)") == 1

    @pytest.mark.parametrize(
        ("endpoint", "path", "payload", "read"),
        [
            pytest.param(
                "post", "/v1/api/serviceTicket/service-tickets/list",
                {"totalCount": 1, "serviceTickets": [{"id": 1, "createdBy": "Ann Lee",
                 "modifiedBy": "Bob Ray Jr", "dueDate": "2026-10-01",
                 "enterStageTS": "2026-09-01 10:00:00"}]},
                lambda c: c.service_tickets.search().service_tickets[0].due_date,
                id="service-ticket-dates-and-names",
            ),
            pytest.param(
                "post", "/v1/api/life", {"totalCount": 1, "alrLeads": [{"id": 1, "status": 4}]},
                lambda c: c.life_health.search().alr_leads[0].status,
                id="life-status-scalar",
            ),
            pytest.param(
                "post", "/v1/api/dashboard-data/sales-data",
                {"agents": [{"monthlyItems": 2.5, "monthlyPolicies": 1.5}]},
                lambda c: c.dashboard.sales_data().agents[0].monthly_items,
                id="dashboard-fractional",
            ),
            pytest.param(
                "get", "/v1/api/leads/1/notes", [{"id": 1, "attr": []}, {"id": 2, "attr": {"k": 1}}],
                lambda c: [n.attr for n in c.leads.notes.list(1)],
                id="note-attr-empty-list",
            ),
            pytest.param(
                "get", "/v1/api/customers/1/policies", [{"id": 1, "tagNames": []}],
                lambda c: c.customers.list_policies(1)[0].tag_names,
                id="policy-tag-list",
            ),
        ],
    )  # fmt: skip
    def test_real_world_shapes_parse_cleanly(
        self,
        api: respx.MockRouter,
        client: AgencyZoom,
        caplog: pytest.LogCaptureFixture,
        endpoint: str,
        path: str,
        payload: object,
        read: object,
    ) -> None:
        """Shapes observed on a live account (2026-10-22) must parse with no warnings."""
        getattr(api, endpoint)(path).mock(return_value=httpx.Response(200, json=payload))
        with caplog.at_level(logging.WARNING, logger="agencyzoom"):
            value = read(client)  # type: ignore[operator]
        assert value is not None
        assert not caplog.records, [r.getMessage() for r in caplog.records]

    def test_retry_after_is_capped(
        self, api: respx.MockRouter, client: AgencyZoom, delays: list[float]
    ) -> None:
        api.get(EMPLOYEES).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "86400"}),
                httpx.Response(200, json=[]),
            ]
        )
        client.settings.employees()
        assert delays == [30.0]  # RetryConfig.max_backoff

    def test_redirects_are_rejected(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        api.get(EMPLOYEES).mock(
            return_value=httpx.Response(301, headers={"Location": f"{BASE_URL}/v1/api/staff"})
        )
        target = api.get("/v1/api/staff").mock(return_value=httpx.Response(200, json=[{"id": 3}]))
        with pytest.raises(AgencyZoomError, match="301"):
            client.settings.employees()
        assert not target.called


# --------------------------------------------------------------------------- pagination


class TestPagination:
    def test_server_ignoring_page_param_does_not_loop_forever(
        self, api: respx.MockRouter, client: AgencyZoom, caplog: pytest.LogCaptureFixture
    ) -> None:
        route = api.post("/v1/api/tasks/list").mock(
            return_value=httpx.Response(200, json={"tasks": [{"id": 1}, {"id": 2}]})
        )
        iterator = client.tasks.paginate(page_size=2)
        assert [next(iterator).id, next(iterator).id] == [1, 2]
        with pytest.raises(APIResponseError, match="same page twice"):
            next(iterator)
        assert route.call_count == 2

    def test_total_count_as_string(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.post("/v1/api/tasks/list").mock(
            return_value=httpx.Response(
                200, json={"totalCount": "2", "tasks": [{"id": 1}, {"id": 2}]}
            )
        )
        assert len(list(client.tasks.paginate(page_size=2))) == 2
        assert route.call_count == 1

    @pytest.mark.parametrize("payload", [{}, {"tasks": None}, {"tasks": "x"}, [], None])
    def test_missing_or_odd_items(
        self, api: respx.MockRouter, client: AgencyZoom, payload: object
    ) -> None:
        api.post("/v1/api/tasks/list").mock(return_value=httpx.Response(200, json=payload))
        with pytest.raises(APIResponseError):
            list(client.tasks.paginate())

    def test_starting_page_is_respected(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.post("/v1/api/tasks/list").mock(
            return_value=httpx.Response(200, json={"tasks": [{"id": 1}]})
        )
        list(client.tasks.paginate(page=3, page_size=10))
        assert sent_json(route)["page"] == 3  # type: ignore[index]


# --------------------------------------------------------------------------- request data


class TestRequestData:
    def test_dates_and_numbers_are_coerced(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.post("/v1/api/leads/list").mock(return_value=httpx.Response(200, json={}))
        client.leads.search(
            start_date=dt.date(2026, 1, 31),
            last_activity_latest_date=dt.datetime(2026, 2, 1, 9, 30),
            customer_phone=5551234,
        )
        assert sent_json(route) == {
            "startDate": "2026-01-31",
            "lastActivityLatestDate": "2026-02-01T09:30:00",
            "customerPhone": "5551234",
        }

    def test_unknown_fields_pass_through(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.post("/v1/api/leads/list").mock(return_value=httpx.Response(200, json={}))
        client.leads.search({"brandNewFilter": [1, 2]})
        assert sent_json(route) == {"brandNewFilter": [1, 2]}

    def test_explicit_none_is_sent_as_null(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.put("/v1/api/tasks/1").mock(return_value=httpx.Response(200, json={}))
        client.tasks.update(1, comments=None)
        assert sent_json(route) == {"comments": None}

    def test_wrong_body_type(self, client: AgencyZoom) -> None:
        with pytest.raises(TypeError, match="body must be"):
            client.leads.search(["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_unicode_round_trip(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.post("/v1/api/leads/5/notes").mock(return_value=httpx.Response(200, json={}))
        client.leads.notes.create(5, "Café ☕ — 東京")
        assert sent_json(route) == {"note": "Café ☕ — 東京"}


class TestUploads:
    def test_text_mode_and_bytes_inputs(self, api: respx.MockRouter, client: AgencyZoom) -> None:
        route = api.post("/v1/api/leads/upload-file").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.leads.files.upload(1, [io.StringIO("plain text"), b"raw", ("a.csv", "x,y")])
        content = route.calls[0].request.content
        assert b"plain text" in content
        assert b"raw" in content
        assert b'filename="a.csv"' in content
        assert b"text/csv" in content

    def test_single_file_not_in_a_list(
        self, api: respx.MockRouter, client: AgencyZoom, tmp_path: Path
    ) -> None:
        path = tmp_path / "one.pdf"
        path.write_bytes(b"%PDF")
        route = api.post("/v1/api/leads/upload-file").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.leads.files.upload(1, path)
        assert b'filename="one.pdf"' in route.calls[0].request.content

    def test_upload_is_retried_with_the_same_content(
        self, api: respx.MockRouter, client: AgencyZoom
    ) -> None:
        route = api.post("/v1/api/leads/upload-file").mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json=[])]
        )
        client.leads.files.upload(1, io.BytesIO(b"stream-content"))
        assert b"stream-content" in route.calls[1].request.content

    @pytest.mark.parametrize(
        ("files", "error"),
        [
            ([], ValueError),
            ("/definitely/missing.pdf", FileNotFoundError),
            ([("only-name",)], ValueError),
            ([123], TypeError),
        ],
    )
    def test_invalid_inputs(self, client: AgencyZoom, files: object, error: type) -> None:
        with pytest.raises(error):
            client.leads.files.upload(1, files)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- lifecycle & concurrency


class TestLifecycle:
    def test_use_after_close(self, api: respx.MockRouter) -> None:
        client = new_client()
        client.close()
        client.close()  # idempotent
        with pytest.raises(AgencyZoomError, match="closed"):
            client.settings.employees()

    def test_closing_parent_closes_copies(self) -> None:
        client = new_client()
        copy = client.with_options(timeout=5)
        client.close()
        with pytest.raises(AgencyZoomError, match="closed"):
            copy.settings.employees()

    def test_user_supplied_http_client_is_not_closed(self) -> None:
        own = httpx.Client()
        with new_client(http_client=own):
            pass
        assert not own.is_closed
        own.close()

    def test_threads_share_one_login(self, api: respx.MockRouter) -> None:
        login = api.post("/v1/api/auth/login").mock(
            return_value=httpx.Response(200, json={"jwt": make_jwt()})
        )
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
        with AgencyZoom("u@x.com", "pw", base_url=BASE_URL) as client, ThreadPoolExecutor(
            8
        ) as pool:
            results = list(pool.map(lambda _: client.settings.employees(), range(32)))
        assert results == [[]] * 32
        assert login.call_count == 1

    def test_async_client_rejects_multiple_event_loops(self, api: respx.MockRouter) -> None:
        """A client and its connection pool belong to one event loop."""
        api.post("/v1/api/auth/login").mock(
            return_value=httpx.Response(200, json={"jwt": make_jwt()})
        )
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
        client = AsyncAgencyZoom("u@x.com", "pw", base_url=BASE_URL)

        async def burst() -> int:
            return len(await asyncio.gather(*(client.settings.employees() for _ in range(5))))

        loop = asyncio.new_event_loop()
        try:
            assert loop.run_until_complete(burst()) == 5
            with pytest.raises(AgencyZoomError, match="one event loop"):
                asyncio.run(burst())
        finally:
            loop.run_until_complete(client.close())
            loop.close()

    def test_rate_limiter_spaces_requests(self, api: respx.MockRouter, delays: list[float]) -> None:
        api.get(EMPLOYEES).mock(return_value=httpx.Response(200, json=[]))
        with new_client(rate_limit_per_minute=2) as client:  # burst of 2, then 30s apart
            for _ in range(4):
                client.settings.employees()
        assert len(delays) == 2
        assert delays[0] == pytest.approx(30, abs=1)
        assert delays[1] == pytest.approx(60, abs=1)
