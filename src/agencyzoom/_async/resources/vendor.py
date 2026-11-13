"""Vendor integrations: ``client.vendor``.

These endpoints let a vendor sync its own records into AgencyZoom, addressing
customers, leads, quotes and policies by the vendor's own string IDs
(``vendorCustomerId``, ``vendorLeadId``, ...) instead of AgencyZoom's integer IDs.

The ``batch_*`` methods use AgencyZoom's enterprise endpoints, which additionally
require an ``X-Api-Token`` header: pass ``api_token`` to the method or the client,
or set ``AGENCYZOOM_API_TOKEN``.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any, Mapping, Sequence

from ..._utils import build_body
from ...models import (
    GenericSuccessResponse,
    VendorBizLeadBatchCreateRequest,
    VendorBizLeadCreateRequest,
    VendorCustomerCreateRequest,
    VendorEnterpriseCustomerBatchCreateRequest,
    VendorEnterpriseCustomerBatchDeleteRequest,
    VendorLeadBatchCreateQuotesRequest,
    VendorLeadBatchCreateRequest,
    VendorLeadBatchDeleteQuotesRequest,
    VendorLeadBatchDeleteRequest,
    VendorLeadBatchMoveToSoldRequest,
    VendorLeadCreateQuoteRequest,
    VendorLeadCreateRequest,
    VendorLeadDeleteRequest,
    VendorLeadMoveToSoldRequest,
    VendorLeadSoldResponse,
    VendorPolicyBatchCreateRequest,
    VendorPolicyBatchDeleteRequest,
    VendorPolicyBatchUpdateStatusRequest,
    VendorPolicyCreateRequest,
    VendorPolicyUpdateStatusRequest,
)
from .._resource import AsyncAPIResource

__all__ = [
    "AsyncVendor",
    "AsyncVendorCustomers",
    "AsyncVendorLeadQuotes",
    "AsyncVendorLeads",
    "AsyncVendorPolicies",
]

Body = Mapping[str, Any]


def _delete_contact(delete_contact: bool | None) -> dict[str, Any]:
    return {} if delete_contact is None else {"delete_contact": delete_contact}


class AsyncVendor(AsyncAPIResource):
    """Sync a vendor's customers, leads, quotes and policies by the vendor's own IDs."""

    @cached_property
    def customers(self) -> AsyncVendorCustomers:
        return AsyncVendorCustomers(self._http)

    @cached_property
    def leads(self) -> AsyncVendorLeads:
        return AsyncVendorLeads(self._http)

    @cached_property
    def policies(self) -> AsyncVendorPolicies:
        return AsyncVendorPolicies(self._http)


class AsyncVendorCustomers(AsyncAPIResource):
    """``client.vendor.customers``"""

    async def create(
        self, body: VendorCustomerCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create a customer. ``POST /vendor/customers/create``"""
        payload = build_body(VendorCustomerCreateRequest, body, fields)
        return await self._call(
            "vendor.customers.create", body=payload, cast_to=GenericSuccessResponse
        )

    async def delete(self, vendor_customer_id: str) -> GenericSuccessResponse:
        """``DELETE /vendor/customers/{vendorCustomerId}``"""
        return await self._call(
            "vendor.customers.delete",
            path_params={"vendor_customer_id": vendor_customer_id},
            cast_to=GenericSuccessResponse,
        )

    async def delete_policy(
        self, vendor_customer_id: str, vendor_policy_id: str
    ) -> GenericSuccessResponse:
        """``DELETE /vendor/customers/{vendorCustomerId}/policies/{vendorPolicyId}``"""
        return await self._call(
            "vendor.customers.delete_policy",
            path_params={
                "vendor_customer_id": vendor_customer_id,
                "vendor_policy_id": vendor_policy_id,
            },
            cast_to=GenericSuccessResponse,
        )

    async def batch_create(
        self,
        body: VendorEnterpriseCustomerBatchCreateRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Create many customers (``customer_create_requests``).
        ``POST /vendor/enterprise/customers/batch-create``"""
        headers = self._api_token_headers("vendor.customers.batch_create", api_token)
        payload = build_body(VendorEnterpriseCustomerBatchCreateRequest, body, fields)
        return await self._call(
            "vendor.customers.batch_create",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_delete(
        self,
        vendor_customer_ids: Sequence[str],
        *,
        delete_contact: bool | None = None,
        api_token: str | None = None,
    ) -> GenericSuccessResponse:
        """``POST /vendor/enterprise/customers/batch-delete``"""
        headers = self._api_token_headers("vendor.customers.batch_delete", api_token)
        payload = build_body(
            VendorEnterpriseCustomerBatchDeleteRequest,
            None,
            {"vendor_customer_ids": list(vendor_customer_ids), **_delete_contact(delete_contact)},
        )
        return await self._call(
            "vendor.customers.batch_delete",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )


class AsyncVendorLeads(AsyncAPIResource):
    """``client.vendor.leads``"""

    @cached_property
    def quotes(self) -> AsyncVendorLeadQuotes:
        return AsyncVendorLeadQuotes(self._http)

    async def create(
        self, body: VendorLeadCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create a personal lead. ``POST /vendor/leads/create``"""
        payload = build_body(VendorLeadCreateRequest, body, fields)
        return await self._call("vendor.leads.create", body=payload, cast_to=GenericSuccessResponse)

    async def create_commercial(
        self, body: VendorBizLeadCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create a commercial lead. ``POST /vendor/leads/create-bizlead``"""
        payload = build_body(VendorBizLeadCreateRequest, body, fields)
        return await self._call(
            "vendor.leads.create_commercial", body=payload, cast_to=GenericSuccessResponse
        )

    async def delete(
        self, vendor_lead_id: str, *, delete_contact: bool | None = None
    ) -> GenericSuccessResponse:
        """``POST /vendor/leads/{vendorLeadId}/delete``"""
        payload = build_body(VendorLeadDeleteRequest, None, _delete_contact(delete_contact))
        return await self._call(
            "vendor.leads.delete",
            path_params={"vendor_lead_id": vendor_lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def mark_sold(
        self,
        vendor_lead_id: str,
        body: VendorLeadMoveToSoldRequest | Body | None = None,
        /,
        **fields: Any,
    ) -> VendorLeadSoldResponse:
        """Move a lead to sold. ``POST /vendor/leads/{vendorLeadId}/sold``"""
        payload = build_body(VendorLeadMoveToSoldRequest, body, fields)
        return await self._call(
            "vendor.leads.mark_sold",
            path_params={"vendor_lead_id": vendor_lead_id},
            body=payload,
            cast_to=VendorLeadSoldResponse,
        )

    async def batch_create(
        self,
        body: VendorLeadBatchCreateRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Create many personal leads (``lead_create_requests``), processed asynchronously.
        ``POST /vendor/enterprise/leads/batch-create``"""
        headers = self._api_token_headers("vendor.leads.batch_create", api_token)
        payload = build_body(VendorLeadBatchCreateRequest, body, fields)
        return await self._call(
            "vendor.leads.batch_create",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_create_commercial(
        self,
        body: VendorBizLeadBatchCreateRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Create many commercial leads (``lead_create_requests``).
        ``POST /vendor/enterprise/leads/batch-create-bizleads``"""
        headers = self._api_token_headers("vendor.leads.batch_create_commercial", api_token)
        payload = build_body(VendorBizLeadBatchCreateRequest, body, fields)
        return await self._call(
            "vendor.leads.batch_create_commercial",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_delete(
        self,
        vendor_lead_ids: Sequence[str],
        *,
        delete_contact: bool | None = None,
        api_token: str | None = None,
    ) -> GenericSuccessResponse:
        """``POST /vendor/enterprise/leads/batch-delete``"""
        headers = self._api_token_headers("vendor.leads.batch_delete", api_token)
        payload = build_body(
            VendorLeadBatchDeleteRequest,
            None,
            {"vendor_lead_ids": list(vendor_lead_ids), **_delete_contact(delete_contact)},
        )
        return await self._call(
            "vendor.leads.batch_delete",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_mark_sold(
        self,
        body: VendorLeadBatchMoveToSoldRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Move many leads to sold (``lead_move_to_sold_requests``).
        ``POST /vendor/enterprise/leads/batch-move-to-sold``"""
        headers = self._api_token_headers("vendor.leads.batch_mark_sold", api_token)
        payload = build_body(VendorLeadBatchMoveToSoldRequest, body, fields)
        return await self._call(
            "vendor.leads.batch_mark_sold",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )


class AsyncVendorLeadQuotes(AsyncAPIResource):
    """``client.vendor.leads.quotes``"""

    async def create(
        self,
        vendor_lead_id: str,
        body: VendorLeadCreateQuoteRequest | Body | None = None,
        /,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """``POST /vendor/leads/{vendorLeadId}/quotes/create``"""
        payload = build_body(VendorLeadCreateQuoteRequest, body, fields)
        return await self._call(
            "vendor.leads.quotes.create",
            path_params={"vendor_lead_id": vendor_lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, vendor_lead_id: str, vendor_quote_id: str) -> GenericSuccessResponse:
        """``DELETE /vendor/leads/{vendorLeadId}/quotes/{vendorQuoteId}``"""
        return await self._call(
            "vendor.leads.quotes.delete",
            path_params={"vendor_lead_id": vendor_lead_id, "vendor_quote_id": vendor_quote_id},
            cast_to=GenericSuccessResponse,
        )

    async def batch_create(
        self,
        body: VendorLeadBatchCreateQuotesRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Create quotes on many leads (``lead_create_quote_requests``).
        ``POST /vendor/enterprise/leads/batch-create-quotes``"""
        headers = self._api_token_headers("vendor.leads.quotes.batch_create", api_token)
        payload = build_body(VendorLeadBatchCreateQuotesRequest, body, fields)
        return await self._call(
            "vendor.leads.quotes.batch_create",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_delete(
        self, vendor_quote_ids: Sequence[str], *, api_token: str | None = None
    ) -> GenericSuccessResponse:
        """``POST /vendor/enterprise/leads/batch-delete-quotes``"""
        headers = self._api_token_headers("vendor.leads.quotes.batch_delete", api_token)
        payload = build_body(
            VendorLeadBatchDeleteQuotesRequest,
            None,
            {"vendor_quote_ids": list(vendor_quote_ids)},
        )
        return await self._call(
            "vendor.leads.quotes.batch_delete",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )


class AsyncVendorPolicies(AsyncAPIResource):
    """``client.vendor.policies``"""

    async def create(
        self, body: VendorPolicyCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /vendor/policies/create``"""
        payload = build_body(VendorPolicyCreateRequest, body, fields)
        return await self._call(
            "vendor.policies.create", body=payload, cast_to=GenericSuccessResponse
        )

    async def update_status(self, vendor_policy_id: str, status: int) -> GenericSuccessResponse:
        """``POST /vendor/policies/update-status``"""
        payload = build_body(
            VendorPolicyUpdateStatusRequest,
            None,
            {"vendor_policy_id": vendor_policy_id, "status": status},
        )
        return await self._call(
            "vendor.policies.update_status", body=payload, cast_to=GenericSuccessResponse
        )

    async def batch_create(
        self,
        body: VendorPolicyBatchCreateRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Create many policies (``policy_create_requests``).
        ``POST /vendor/enterprise/policies/batch-create``"""
        headers = self._api_token_headers("vendor.policies.batch_create", api_token)
        payload = build_body(VendorPolicyBatchCreateRequest, body, fields)
        return await self._call(
            "vendor.policies.batch_create",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_update_status(
        self,
        body: VendorPolicyBatchUpdateStatusRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Update many policy statuses (``policy_update_status_requests``).
        ``POST /vendor/enterprise/policies/batch-update-status``"""
        headers = self._api_token_headers("vendor.policies.batch_update_status", api_token)
        payload = build_body(VendorPolicyBatchUpdateStatusRequest, body, fields)
        return await self._call(
            "vendor.policies.batch_update_status",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )

    async def batch_delete(
        self, vendor_policy_ids: Sequence[str], *, api_token: str | None = None
    ) -> GenericSuccessResponse:
        """``POST /vendor/enterprise/policies/batch-delete``"""
        headers = self._api_token_headers("vendor.policies.batch_delete", api_token)
        payload = build_body(
            VendorPolicyBatchDeleteRequest,
            None,
            {"vendor_policy_ids": list(vendor_policy_ids)},
        )
        return await self._call(
            "vendor.policies.batch_delete",
            body=payload,
            headers=headers,
            cast_to=GenericSuccessResponse,
        )
