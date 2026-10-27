"""The endpoint registry: the single place where API paths are defined.

Paths are relative to the API root (``/v1/api`` by default), so switching API
versions is a configuration change rather than a code change::

    AgencyZoom(api_version="v2")                       # every endpoint -> /v2/api/...
    AgencyZoom(api_root="/api/v2")                     # a different root layout
    AgencyZoom(endpoint_overrides={                    # move individual endpoints
        "leads.search": "POST /v2/api/leads/search",   #   method + absolute path
        "leads.get": "/v2/api/leads/{lead_id}",        #   path only (method kept)
    })

Endpoint IDs mirror the SDK attribute path (``client.leads.notes.create`` ->
``"leads.notes.create"``); paginated ``paginate()`` methods share the ID of the
matching ``search``.
"""

from __future__ import annotations

import difflib
import re
from typing import Mapping, NamedTuple
from urllib.parse import quote

from ._exceptions import ConfigurationError

__all__ = ["ENDPOINTS", "Endpoint", "EndpointResolver"]

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class Endpoint(NamedTuple):
    method: str
    path: str
    """Relative to the API root, unless the endpoint came from an override."""


ENDPOINTS: dict[str, Endpoint] = {
    "auth.login": Endpoint("POST", "/auth/login"),
    "auth.logout": Endpoint("POST", "/auth/logout"),
    "auth.refresh": Endpoint("POST", "/auth/refresh"),
    "auth.sso_login": Endpoint("POST", "/auth/ssologin"),
    "business_classifications.search": Endpoint("POST", "/get-classifications"),
    "contacts.batch_create": Endpoint("POST", "/contact/batch-create"),
    "customers.add_note": Endpoint("POST", "/customers/{customer_id}/notes"),
    "customers.create": Endpoint("POST", "/customers/create"),
    "customers.delete_file": Endpoint("DELETE", "/customers/{customer_id}/files/{file_id}"),
    "customers.delete_policy": Endpoint("DELETE", "/customers/{customer_id}/policies/{policy_id}"),
    "customers.delete": Endpoint("DELETE", "/customers/{customer_id}"),
    "customers.get": Endpoint("GET", "/customers/{customer_id}"),
    "customers.list_ams_policies": Endpoint("GET", "/customers/{customer_id}/ams-policies"),
    "customers.list_policies": Endpoint("GET", "/customers/{customer_id}/policies"),
    "customers.list_tasks": Endpoint("GET", "/customers/{customer_id}/tasks"),
    "customers.search": Endpoint("POST", "/customers"),
    "customers.update": Endpoint("PUT", "/customers/{customer_id}"),
    "dashboard.sales_data": Endpoint("POST", "/dashboard-data/sales-data"),
    "departments.list": Endpoint("POST", "/department-groups"),
    "email_threads.delete_message": Endpoint("POST", "/email-thread/delete-message"),
    "email_threads.delete": Endpoint("POST", "/email-thread/delete-thread"),
    "email_threads.get_messages": Endpoint("POST", "/email-thread/email-thread-detail"),
    "email_threads.mark_unread": Endpoint("POST", "/email-thread/unread-thread"),
    "email_threads.search": Endpoint("POST", "/email-thread/list"),
    "leads.batch_create": Endpoint("POST", "/leads/batch-create"),
    "leads.change_stage": Endpoint("PUT", "/leads/{lead_id}/stage"),
    "leads.change_status": Endpoint("PUT", "/leads/{lead_id}/status"),
    "leads.count": Endpoint("POST", "/leads/pipeline-count"),
    "leads.create_commercial": Endpoint("POST", "/leads/create-biz-lead"),
    "leads.create": Endpoint("POST", "/leads/create"),
    "leads.delete": Endpoint("POST", "/leads/{lead_id}/delete-lead"),
    "leads.files.delete": Endpoint("DELETE", "/leads/{lead_id}/files/{file_id}"),
    "leads.files.list": Endpoint("POST", "/leads/files"),
    "leads.files.rename": Endpoint("PUT", "/leads/{lead_id}/rename"),
    "leads.files.upload": Endpoint("POST", "/leads/upload-file"),
    "leads.get": Endpoint("GET", "/leads/{lead_id}"),
    "leads.list_tasks": Endpoint("GET", "/leads/{lead_id}/tasks"),
    "leads.mark_sold": Endpoint("POST", "/leads/{lead_id}/sold"),
    "leads.notes.create": Endpoint("POST", "/leads/{lead_id}/notes"),
    "leads.notes.list": Endpoint("GET", "/leads/{lead_id}/notes"),
    "leads.opportunities.create": Endpoint("POST", "/leads/{lead_id}/opportunities"),
    "leads.opportunities.delete": Endpoint(
        "DELETE", "/leads/{lead_id}/opportunities/{opportunity_id}"
    ),
    "leads.opportunities.list": Endpoint("GET", "/leads/{lead_id}/opportunities"),
    "leads.opportunities.update": Endpoint("PUT", "/leads/{lead_id}/opportunities"),
    "leads.quotes.create": Endpoint("POST", "/leads/{lead_id}/quotes"),
    "leads.quotes.delete": Endpoint("DELETE", "/leads/{lead_id}/quotes/{quote_id}"),
    "leads.quotes.list": Endpoint("GET", "/leads/{lead_id}/quotes"),
    "leads.quotes.update": Endpoint("PUT", "/leads/{lead_id}/quotes"),
    "leads.recycle_events": Endpoint("GET", "/{lead_id}/recycle-events"),
    "leads.search": Endpoint("POST", "/leads/list"),
    "leads.update_commercial": Endpoint("PUT", "/leads/{lead_id}/update-biz-lead"),
    "leads.update": Endpoint("PUT", "/leads/{lead_id}"),
    "life_health.search": Endpoint("POST", "/life"),
    "opportunities.create": Endpoint("POST", "/opportunities"),
    "opportunities.delete": Endpoint("DELETE", "/opportunities/{opportunity_id}"),
    "opportunities.drivers.create": Endpoint("POST", "/opportunities/{opportunity_id}/driver"),
    "opportunities.drivers.delete": Endpoint("DELETE", "/opportunities/drivers/{driver_id}"),
    "opportunities.drivers.get": Endpoint("GET", "/opportunities/drivers/{driver_id}"),
    "opportunities.drivers.link": Endpoint(
        "PUT", "/opportunities/{opportunity_id}/link-driver/{driver_id}"
    ),
    "opportunities.drivers.list": Endpoint("GET", "/opportunities/{opportunity_id}/drivers"),
    "opportunities.drivers.unlink": Endpoint(
        "PUT", "/opportunities/{opportunity_id}/unlink-driver/{driver_id}"
    ),
    "opportunities.drivers.update": Endpoint("PUT", "/opportunities/drivers/{driver_id}"),
    "opportunities.get": Endpoint("GET", "/opportunities/{opportunity_id}"),
    "opportunities.update": Endpoint("PUT", "/opportunities/{opportunity_id}"),
    "opportunities.vehicles.create": Endpoint("POST", "/opportunities/{opportunity_id}/vehicle"),
    "opportunities.vehicles.delete": Endpoint("DELETE", "/opportunities/vehicles/{vehicle_id}"),
    "opportunities.vehicles.get": Endpoint("GET", "/opportunities/vehicles/{vehicle_id}"),
    "opportunities.vehicles.link": Endpoint(
        "PUT", "/opportunities/{opportunity_id}/link-vehicle/{vehicle_id}"
    ),
    "opportunities.vehicles.list": Endpoint("GET", "/opportunities/{opportunity_id}/vehicles"),
    "opportunities.vehicles.unlink": Endpoint(
        "PUT", "/opportunities/{opportunity_id}/unlink-vehicle/{vehicle_id}"
    ),
    "opportunities.vehicles.update": Endpoint("PUT", "/opportunities/vehicles/{vehicle_id}"),
    "pipelines.end_stages": Endpoint("GET", "/end-stages"),
    "pipelines.list_with_stages": Endpoint("GET", "/pipelines-and-stages"),
    "pipelines.list": Endpoint("GET", "/pipelines"),
    "policies.create": Endpoint("POST", "/policies/create"),
    "policies.endorse": Endpoint("POST", "/policies/endorse"),
    "policies.update_status": Endpoint("POST", "/policies/update-status"),
    "policies.update_tags": Endpoint("POST", "/policies/update-tags"),
    "policies.update": Endpoint("PUT", "/policies/{policy_id}"),
    "profile.update": Endpoint("PUT", "/profile/my"),
    "service_tickets.complete": Endpoint(
        "POST", "/serviceTicket/service-tickets/{ticket_id}/complete"
    ),
    "service_tickets.create": Endpoint("POST", "/serviceTicket/service-tickets/create"),
    "service_tickets.list_ams_policies": Endpoint(
        "GET", "/serviceTicket/service-tickets/{ticket_id}/ams-policies"
    ),
    "service_tickets.list_policies": Endpoint(
        "GET", "/serviceTicket/service-tickets/{ticket_id}/policies"
    ),
    "service_tickets.search": Endpoint("POST", "/serviceTicket/service-tickets/list"),
    "service_tickets.update": Endpoint("PUT", "/serviceTicket/service-tickets/{ticket_id}"),
    "settings.assign_groups": Endpoint("GET", "/assign-groups"),
    "settings.carriers": Endpoint("GET", "/carriers"),
    "settings.csrs": Endpoint("GET", "/csrs"),
    "settings.custom_fields": Endpoint("GET", "/custom-fields"),
    "settings.employees": Endpoint("GET", "/employees"),
    "settings.lead_source_categories": Endpoint("GET", "/lead-source-categories"),
    "settings.lead_sources": Endpoint("GET", "/lead-sources"),
    "settings.life_professionals": Endpoint("GET", "/life-professionals"),
    "settings.locations": Endpoint("GET", "/locations"),
    "settings.loss_reasons": Endpoint("GET", "/loss-reasons"),
    "settings.product_categories": Endpoint("GET", "/product-categories"),
    "settings.product_lines": Endpoint("GET", "/product-lines"),
    "settings.service_categories": Endpoint("GET", "/service-categories"),
    "settings.service_priorities": Endpoint("GET", "/service-priorities"),
    "settings.service_resolutions": Endpoint("GET", "/service-resolutions"),
    "settings.tags": Endpoint("GET", "/tags"),
    "tasks.batch_delete": Endpoint("POST", "/tasks/batch-delete"),
    "tasks.complete": Endpoint("PUT", "/tasks/{task_id}/completed"),
    "tasks.create": Endpoint("POST", "/tasks"),
    "tasks.delete": Endpoint("DELETE", "/tasks/{task_id}"),
    "tasks.get": Endpoint("GET", "/tasks/{task_id}"),
    "tasks.reopen": Endpoint("PUT", "/tasks/{task_id}/reopened"),
    "tasks.search": Endpoint("POST", "/tasks/list"),
    "tasks.update": Endpoint("PUT", "/tasks/{task_id}"),
    "text_threads.delete": Endpoint("POST", "/text-thread/delete-thread"),
    "text_threads.get_messages": Endpoint("POST", "/text-thread/text-thread-detail"),
    "text_threads.list_producers": Endpoint("GET", "/text-thread/producer"),
    "text_threads.mark_unread": Endpoint("POST", "/text-thread/unread-thread"),
    "text_threads.search": Endpoint("POST", "/text-thread/list"),
    "v4sso.get_auth_params": Endpoint("POST", "/v4sso/get-auth-params"),
    "v4sso.login": Endpoint("POST", "/v4sso/sso-login"),
}


def placeholders(path: str) -> frozenset[str]:
    return frozenset(_PLACEHOLDER.findall(path))


class EndpointResolver:
    """Turns an endpoint ID plus path parameters into ``(method, absolute path)``."""

    __slots__ = ("_api_root", "_overrides")

    def __init__(self, api_root: str, overrides: Mapping[str, str] | None = None) -> None:
        self._api_root = "/" + api_root.strip("/") if api_root.strip("/") else ""
        self._overrides: dict[str, Endpoint] = {
            key: _parse_override(key, value) for key, value in (overrides or {}).items()
        }

    @property
    def api_root(self) -> str:
        return self._api_root

    def resolve(
        self, endpoint_id: str, path_params: Mapping[str, object] | None = None
    ) -> tuple[str, str]:
        override = self._overrides.get(endpoint_id)
        if override is not None:
            method, path = override
        else:
            try:
                method, relative = ENDPOINTS[endpoint_id]
            except KeyError:
                raise KeyError(f"Unknown AgencyZoom endpoint {endpoint_id!r}") from None
            path = f"{self._api_root}{relative}"
        return method, format_path(path, path_params or {})


def format_path(template: str, params: Mapping[str, object]) -> str:
    """Substitute ``{name}`` placeholders with validated, URL-encoded values."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise KeyError(f"Missing path parameter {name!r} for {template!r}")
        value = params[name]
        # bool is an int subclass: `get(True)` is almost certainly a bug.
        text = str(value).strip()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, str))
            or not re.fullmatch(r"[0-9]+", text)
        ):
            raise ValueError(f"{name} must be a non-negative integer ID")
        return quote(text, safe="")

    return _PLACEHOLDER.sub(substitute, template)


def _parse_override(endpoint_id: str, value: str) -> Endpoint:
    if endpoint_id not in ENDPOINTS:
        close = difflib.get_close_matches(endpoint_id, ENDPOINTS, n=1)
        hint = f" Did you mean {close[0]!r}?" if close else ""
        raise ConfigurationError(f"Unknown endpoint in endpoint_overrides: {endpoint_id!r}.{hint}")
    original = ENDPOINTS[endpoint_id]
    parts = value.strip().split(None, 1)
    if len(parts) == 2 and parts[0].upper() in _METHODS:
        method, path = parts[0].upper(), parts[1].strip()
    else:
        method, path = original.method, value.strip()
    if not path.startswith("/"):
        raise ConfigurationError(
            f"endpoint_overrides[{endpoint_id!r}] must be an absolute path such as "
            f"'/v2/api/...', got {value!r}"
        )
    if placeholders(path) != placeholders(original.path):
        expected = ", ".join(sorted(placeholders(original.path))) or "none"
        raise ConfigurationError(
            f"endpoint_overrides[{endpoint_id!r}] must use the same path parameters "
            f"as the original ({expected}), got {value!r}"
        )
    return Endpoint(method, path)
