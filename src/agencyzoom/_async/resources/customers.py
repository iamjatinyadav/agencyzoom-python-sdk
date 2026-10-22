"""Customer management: ``client.customers``."""

from __future__ import annotations

from typing import Any, AsyncIterator, List, Mapping, Union, cast

from ..._utils import build_body
from ...models import (
    AmsPolicy,
    CustomerCreateRequest,
    CustomerDetail,
    CustomerSearchRequest,
    CustomerSearchResponse,
    CustomerSummary,
    CustomerUpdateRequest,
    GenericSuccessResponse,
    NoteRequest,
    Task,
    WrittenPolicy,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncCustomers"]

Body = Mapping[str, Any]

# The spec documents a single object here, while the equivalent service-ticket
# endpoints return arrays; accept either shape.
AmsPolicies = Union[List[AmsPolicy], AmsPolicy]
WrittenPolicies = Union[List[WrittenPolicy], WrittenPolicy]


class AsyncCustomers(AsyncAPIResource):
    """Search, create and manage customers, their notes, files and policies."""

    async def search(
        self, body: CustomerSearchRequest | Body | None = None, /, **filters: Any
    ) -> CustomerSearchResponse:
        """Search customers (one page). ``POST /customers``"""
        payload = build_body(CustomerSearchRequest, body, filters)
        return await self._call("customers.search", body=payload, cast_to=CustomerSearchResponse)

    def paginate(
        self, body: CustomerSearchRequest | Body | None = None, /, **filters: Any
    ) -> AsyncIterator[CustomerSummary]:
        """Iterate over every matching customer, fetching pages lazily."""
        payload = build_body(CustomerSearchRequest, body, filters)
        return self._paginate(
            "customers.search",
            payload,
            items_key="customers",
            item_type=CustomerSummary,
            page_size=100,
        )

    async def get(self, customer_id: int) -> CustomerDetail:
        """``GET /customers/{customerId}``"""
        return await self._call(
            "customers.get", path_params={"customer_id": customer_id}, cast_to=CustomerDetail
        )

    async def create(
        self, body: CustomerCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /customers/create``"""
        payload = build_body(CustomerCreateRequest, body, fields)
        return await self._call("customers.create", body=payload, cast_to=GenericSuccessResponse)

    async def update(
        self, customer_id: int, body: CustomerUpdateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``PUT /customers/{customerId}``"""
        payload = build_body(CustomerUpdateRequest, body, fields)
        return await self._call(
            "customers.update",
            path_params={"customer_id": customer_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, customer_id: int) -> GenericSuccessResponse:
        """``DELETE /customers/{customerId}``"""
        return await self._call(
            "customers.delete",
            path_params={"customer_id": customer_id},
            cast_to=GenericSuccessResponse,
        )

    async def list_tasks(self, customer_id: int) -> list[Task]:
        """``GET /customers/{customerId}/tasks``"""
        return await self._call(
            "customers.list_tasks", path_params={"customer_id": customer_id}, cast_to=List[Task]
        )

    async def add_note(self, customer_id: int, note: str) -> GenericSuccessResponse:
        """``POST /customers/{customerId}/notes``"""
        payload = build_body(NoteRequest, None, {"note": note})
        return await self._call(
            "customers.add_note",
            path_params={"customer_id": customer_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete_file(self, customer_id: int, file_id: int) -> GenericSuccessResponse:
        """``DELETE /customers/{customerId}/files/{fileId}``"""
        return await self._call(
            "customers.delete_file",
            path_params={"customer_id": customer_id, "file_id": file_id},
            cast_to=GenericSuccessResponse,
        )

    async def list_policies(self, customer_id: int) -> list[WrittenPolicy] | WrittenPolicy:
        """Policies written in AgencyZoom. ``GET /customers/{customerId}/policies``"""
        result = await self._call(
            "customers.list_policies",
            path_params={"customer_id": customer_id},
            cast_to=WrittenPolicies,
        )
        return cast("list[WrittenPolicy] | WrittenPolicy", result)

    async def list_ams_policies(self, customer_id: int) -> list[AmsPolicy] | AmsPolicy:
        """Policies synced from the AMS. ``GET /customers/{customerId}/ams-policies``"""
        result = await self._call(
            "customers.list_ams_policies",
            path_params={"customer_id": customer_id},
            cast_to=AmsPolicies,
        )
        return cast("list[AmsPolicy] | AmsPolicy", result)

    async def delete_policy(self, customer_id: int, policy_id: int) -> GenericSuccessResponse:
        """``DELETE /customers/{customerId}/policies/{policyId}``"""
        return await self._call(
            "customers.delete_policy",
            path_params={"customer_id": customer_id, "policy_id": policy_id},
            cast_to=GenericSuccessResponse,
        )
