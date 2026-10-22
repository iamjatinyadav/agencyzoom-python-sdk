"""Smaller API groups, one class each, mirroring the AgencyZoom API reference."""

from __future__ import annotations

from typing import Any, AsyncIterator, List, Mapping

from ..._utils import build_body
from ...models import (
    AlrapptsSummary,
    BatchContactDataRequest,
    BusinessClassificationRequest,
    BusinessClassificationResponse,
    DashboardData,
    DashboardDataRequest,
    DepartmentGroups,
    DepartmentGroupsRequest,
    GenericSuccessResponse,
    LifeSearchRequest,
    LifeSearchResponse,
    UpdateProfileRequest,
)
from .._resource import AsyncAPIResource

__all__ = [
    "AsyncBusinessClassifications",
    "AsyncContacts",
    "AsyncDashboard",
    "AsyncDepartments",
    "AsyncLifeHealth",
    "AsyncProfile",
]

Body = Mapping[str, Any]


class AsyncContacts(AsyncAPIResource):
    """Contact management: ``client.contacts``."""

    async def batch_create(
        self, body: BatchContactDataRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /contact/batch-create``"""
        payload = build_body(BatchContactDataRequest, body, fields)
        return await self._call(
            "contacts.batch_create", body=payload, cast_to=GenericSuccessResponse
        )


class AsyncDashboard(AsyncAPIResource):
    """Dashboard data: ``client.dashboard``."""

    async def sales_data(
        self, body: DashboardDataRequest | Body | None = None, /, **filters: Any
    ) -> DashboardData:
        """Summary sales figures. ``POST /dashboard-data/sales-data``"""
        payload = build_body(DashboardDataRequest, body, filters)
        return await self._call("dashboard.sales_data", body=payload, cast_to=DashboardData)


class AsyncLifeHealth(AsyncAPIResource):
    """Life & health leads: ``client.life_health``."""

    async def search(
        self, body: LifeSearchRequest | Body | None = None, /, **filters: Any
    ) -> LifeSearchResponse:
        """``POST /life``"""
        payload = build_body(LifeSearchRequest, body, filters)
        return await self._call("life_health.search", body=payload, cast_to=LifeSearchResponse)

    def paginate(
        self, body: LifeSearchRequest | Body | None = None, /, **filters: Any
    ) -> AsyncIterator[AlrapptsSummary]:
        """Iterate over every matching life & health lead, fetching pages lazily."""
        payload = build_body(LifeSearchRequest, body, filters)
        return self._paginate(
            "life_health.search",
            payload,
            items_key="alrLeads",
            item_type=AlrapptsSummary,
            page_size=500,
        )


class AsyncProfile(AsyncAPIResource):
    """The authenticated user's profile: ``client.profile``."""

    async def update(
        self, body: UpdateProfileRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``PUT /profile/my``"""
        payload = build_body(UpdateProfileRequest, body, fields)
        return await self._call("profile.update", body=payload, cast_to=GenericSuccessResponse)


class AsyncDepartments(AsyncAPIResource):
    """Departments and groups: ``client.departments``."""

    async def list(self, agency_number: str | None = None) -> DepartmentGroups:
        """``POST /department-groups``"""
        fields = {} if agency_number is None else {"agency_number": agency_number}
        payload = build_body(DepartmentGroupsRequest, None, fields)
        return await self._call("departments.list", body=payload, cast_to=DepartmentGroups)


class AsyncBusinessClassifications(AsyncAPIResource):
    """Business (commercial) classifications: ``client.business_classifications``."""

    async def search(
        self, body: BusinessClassificationRequest | Body | None = None, /, **filters: Any
    ) -> list[BusinessClassificationResponse]:
        """``POST /get-classifications``"""
        payload = build_body(BusinessClassificationRequest, body, filters)
        return await self._call(
            "business_classifications.search",
            body=payload,
            cast_to=List[BusinessClassificationResponse],
        )
