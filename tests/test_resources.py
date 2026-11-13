"""Request shaping and response parsing for representative endpoints."""

from __future__ import annotations

import io
import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from agencyzoom import AgencyZoom, AsyncAgencyZoom, ConfigurationError
from agencyzoom.models import LeadSearchRequest

from .conftest import BASE_URL, make_jwt

VALID_POLICY = {
    "customer_id": 1,
    "carrier_id": 2,
    "policy_type": 3,
    "agent_id": 4,
    "lead_source_id": 5,
    "agency_number": "A1",
    "premium": 1200,
    "items": 1,
    "sold_date": "2026-01-01",
    "effective_date": "2026-01-01",
    "expiry_date": "2027-01-01",
}


def body(route: respx.Route, index: int = 0) -> object:
    return json.loads(route.calls[index].request.content)


def test_search_accepts_snake_case_kwargs(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.post("/v1/api/leads/list").mock(
        return_value=httpx.Response(
            200,
            json={"totalCount": 1, "leads": [{"id": 7, "firstname": "Ada", "unknownNewField": 1}]},
        )
    )
    result = client.leads.search(status=0, page_size=25, customer_email="ada@")
    assert body(route) == {"status": 0, "pageSize": 25, "customerEmail": "ada@"}
    assert result.total_count == 1
    lead = result.leads[0]
    assert (lead.id, lead.firstname) == (7, "Ada")
    assert lead["unknownNewField"] == 1  # unknown fields are preserved


def test_model_and_dict_bodies_are_equivalent(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.post("/v1/api/leads/list").mock(return_value=httpx.Response(200, json={}))
    client.leads.search(LeadSearchRequest(page_size=10))
    client.leads.search({"pageSize": 10})
    client.leads.search({"pageSize": 99}, page_size=10)  # kwargs win
    assert body(route, 0) == body(route, 1) == body(route, 2) == {"pageSize": 10}


def test_required_fields_are_validated_client_side(client: AgencyZoom) -> None:
    with pytest.raises(ValidationError, match="email"):
        client.leads.create(firstname="Ada")


def test_paginate_walks_all_pages(api: respx.MockRouter, client: AgencyZoom) -> None:
    pages = [
        {"totalCount": 5, "customers": [{"id": 1}, {"id": 2}]},
        {"totalCount": 5, "customers": [{"id": 3}, {"id": 4}]},
        {"totalCount": 5, "customers": [{"id": 5}]},
    ]
    route = api.post("/v1/api/customers").mock(
        side_effect=[httpx.Response(200, json=p) for p in pages]
    )
    ids = [c.id for c in client.customers.paginate(page_size=2, state="TX")]
    assert ids == [1, 2, 3, 4, 5]
    assert [body(route, i)["page"] for i in range(3)] == [0, 1, 2]  # type: ignore[index]
    assert body(route, 0)["state"] == "TX"  # type: ignore[index]


def test_paginate_is_lazy(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.post("/v1/api/tasks/list").mock(
        return_value=httpx.Response(200, json={"totalCount": 1000, "tasks": [{"id": 1}] * 200})
    )
    iterator = client.tasks.paginate()
    assert route.call_count == 0
    next(iterator)
    assert route.call_count == 1
    assert body(route)["pageSize"] == 200  # type: ignore[index]  # endpoint maximum by default


async def test_async_paginate(api: respx.MockRouter, aclient: AsyncAgencyZoom) -> None:
    api.post("/v1/api/serviceTicket/service-tickets/list").mock(
        side_effect=[
            httpx.Response(200, json={"totalCount": 3, "serviceTickets": [{"id": 1}, {"id": 2}]}),
            httpx.Response(200, json={"totalCount": 3, "serviceTickets": [{"id": 3}]}),
        ]
    )
    ids = [t.id async for t in aclient.service_tickets.paginate(page_size=2)]
    assert ids == [1, 2, 3]


def test_path_parameters(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.put("/v1/api/opportunities/11/link-driver/22").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    assert client.opportunities.drivers.link(11, 22).result is True
    assert route.called


def test_nested_resources(api: respx.MockRouter, client: AgencyZoom) -> None:
    api.get("/v1/api/leads/3/notes").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "body": "hi"}])
    )
    create = api.post("/v1/api/leads/3/notes").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    assert client.leads.notes.list(3)[0].id == 1
    client.leads.notes.create(3, "Called, left voicemail")
    assert body(create) == {"note": "Called, left voicemail"}


def test_upload_files_multipart(api: respx.MockRouter, client: AgencyZoom, tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "dec-page.pdf"
    path.write_bytes(b"%PDF-1.7")
    route = api.post("/v1/api/leads/upload-file").mock(
        return_value=httpx.Response(200, json=[{"id": 1}, {"id": 2}])
    )
    files = client.leads.files.upload(42, [path, ("notes.txt", io.BytesIO(b"hello"))])
    assert [f.id for f in files] == [1, 2]
    request = route.calls[0].request
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    content = request.content
    assert b'name="entityId"' in content
    assert b"42" in content
    assert b'filename="dec-page.pdf"' in content
    assert b"application/pdf" in content
    assert b'filename="notes.txt"' in content


def test_policy_create_sends_api_token(api: respx.MockRouter) -> None:
    route = api.post("/v1/api/policies/create").mock(
        return_value=httpx.Response(200, json={"result": True, "id": 5})
    )
    with AgencyZoom(token=make_jwt(), base_url=BASE_URL, api_token="secret") as client:
        client.policies.create(VALID_POLICY)
    assert route.calls[0].request.headers["X-Api-Token"] == "secret"


def test_policy_create_requires_api_token(client: AgencyZoom) -> None:
    with pytest.raises(ConfigurationError, match="API token"):
        client.policies.create(VALID_POLICY)


def test_pipelines_query_param(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.get("/v1/api/pipelines", params={"type": "service"}).mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "Service"}])
    )
    assert client.pipelines.list("service")[0].name == "Service"
    assert route.called


def test_malformed_response_fields_are_tolerated(
    api: respx.MockRouter, client: AgencyZoom, caplog: pytest.LogCaptureFixture
) -> None:
    api.get("/v1/api/tasks/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "status": "", "title": "Call", "customerId": "not-a-number"}
        )
    )
    task = client.tasks.get(1)
    assert (task.id, task.title) == (1, "Call")
    assert task.status is None  # "" -> None
    assert task.customer_id is None  # invalid -> None, with a warning
    assert "customerId (int_parsing)" in caplog.text


def test_batch_delete_tasks(api: respx.MockRouter, client: AgencyZoom) -> None:
    route = api.post("/v1/api/tasks/batch-delete").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    client.tasks.batch_delete(i for i in (1, 2, 3))
    assert body(route) == {"taskIds": [1, 2, 3]}


# ------------------------------------------------------------------- vendor


def test_vendor_ids_are_strings_encoded_as_one_segment(
    api: respx.MockRouter, client: AgencyZoom
) -> None:
    route = api.delete("/v1/api/vendor/leads/crm%2F1%20a/quotes/q-7").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    client.vendor.leads.quotes.delete("crm/1 a", "q-7")
    assert route.call_count == 1


@pytest.mark.parametrize("bad", ["", " ", ".", "..", "a\nb", None, True, 1.5])
def test_vendor_ids_reject_unsafe_values(client: AgencyZoom, bad: object) -> None:
    with pytest.raises(ValueError, match="vendor_customer_id"):
        client.vendor.customers.delete(bad)  # type: ignore[arg-type]


def test_vendor_mark_sold_shapes_body_and_parses_response(
    api: respx.MockRouter, client: AgencyZoom
) -> None:
    route = api.post("/v1/api/vendor/leads/L-1/sold").mock(
        return_value=httpx.Response(200, json={"vendorCustomerId": "C-1", "leadSourceId": 3})
    )
    result = client.vendor.leads.mark_sold(
        "L-1",
        vendor_customer_id="C-1",
        sold_products=[{"vendor_quote_id": "Q-1", "location_id": "LOC", "is_sold": True}],
    )
    assert body(route) == {
        "vendorCustomerId": "C-1",
        "soldProducts": [{"vendorQuoteId": "Q-1", "locationId": "LOC", "isSold": True}],
    }
    assert (result.vendor_customer_id, result.lead_source_id) == ("C-1", 3)


def test_vendor_batch_methods_send_api_token(api: respx.MockRouter) -> None:
    route = api.post("/v1/api/vendor/enterprise/leads/batch-delete").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    with AgencyZoom(token=make_jwt(), base_url=BASE_URL, api_token="secret") as client:
        client.vendor.leads.batch_delete(["L-1", "L-2"], delete_contact=True)
        client.vendor.leads.batch_delete(["L-3"], api_token="override")
    assert body(route, 0) == {"vendorLeadIds": ["L-1", "L-2"], "deleteContact": True}
    assert route.calls[0].request.headers["X-Api-Token"] == "secret"
    assert route.calls[1].request.headers["X-Api-Token"] == "override"


def test_vendor_batch_methods_require_api_token(api: respx.MockRouter, client: AgencyZoom) -> None:
    with pytest.raises(ConfigurationError, match=r"vendor\.policies\.batch_delete requires an API"):
        client.vendor.policies.batch_delete(["P-1"])
    assert not api.calls


def test_vendor_single_record_methods_do_not_need_api_token(
    api: respx.MockRouter, client: AgencyZoom
) -> None:
    route = api.post("/v1/api/vendor/policies/update-status").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    client.vendor.policies.update_status("P-1", 2)
    assert body(route) == {"vendorPolicyId": "P-1", "status": 2}
    assert "X-Api-Token" not in route.calls[0].request.headers


async def test_async_vendor_batch_create(api: respx.MockRouter) -> None:
    route = api.post("/v1/api/vendor/enterprise/customers/batch-create").mock(
        return_value=httpx.Response(200, json={"result": True})
    )
    customer = {"vendor_customer_id": "C-1", "agent_id": 4, "email": "a@b.c", "firstname": "Ada"}
    async with AsyncAgencyZoom(token=make_jwt(), base_url=BASE_URL, api_token="t") as client:
        await client.vendor.customers.batch_create(customer_create_requests=[customer])
    assert body(route) == {
        "customerCreateRequests": [
            {"vendorCustomerId": "C-1", "agentId": 4, "email": "a@b.c", "firstname": "Ada"}
        ]
    }
