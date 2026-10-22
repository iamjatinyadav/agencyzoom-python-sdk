"""Agency configuration and reference data: ``client.settings``.

These lists change rarely. Construct the client with ``cache_ttl=...`` and they're
served from memory after the first call, saving rate-limit budget.
"""

from __future__ import annotations

from typing import List

from ...models import (
    AssignGroup,
    Carrier,
    CsrResponse,
    CustomFieldDef,
    Employee,
    LeadSource,
    LeadSourceCategory,
    LifeProfessional,
    Location,
    LossReason,
    ProductCategory,
    ProductLine,
    ServiceCategory,
    ServicePriority,
    ServiceResolution,
    TagResponse,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncSettings"]


class AsyncSettings(AsyncAPIResource):
    """Read-only reference lists used to fill IDs in other requests."""

    async def product_categories(self) -> list[ProductCategory]:
        """Policy categories. ``GET /product-categories``"""
        return await self._call(
            "settings.product_categories", cast_to=List[ProductCategory], cache=True
        )

    async def product_lines(self) -> list[ProductLine]:
        """Policy types. ``GET /product-lines``"""
        return await self._call("settings.product_lines", cast_to=List[ProductLine], cache=True)

    async def employees(self) -> list[Employee]:
        """``GET /employees``"""
        return await self._call("settings.employees", cast_to=List[Employee], cache=True)

    async def life_professionals(self) -> list[LifeProfessional]:
        """``GET /life-professionals``"""
        return await self._call(
            "settings.life_professionals", cast_to=List[LifeProfessional], cache=True
        )

    async def lead_sources(self) -> list[LeadSource]:
        """``GET /lead-sources``"""
        return await self._call("settings.lead_sources", cast_to=List[LeadSource], cache=True)

    async def lead_source_categories(self) -> list[LeadSourceCategory]:
        """``GET /lead-source-categories``"""
        return await self._call(
            "settings.lead_source_categories", cast_to=List[LeadSourceCategory], cache=True
        )

    async def service_categories(self) -> list[ServiceCategory]:
        """``GET /service-categories``"""
        return await self._call(
            "settings.service_categories", cast_to=List[ServiceCategory], cache=True
        )

    async def service_priorities(self) -> list[ServicePriority]:
        """``GET /service-priorities``"""
        return await self._call(
            "settings.service_priorities", cast_to=List[ServicePriority], cache=True
        )

    async def service_resolutions(self) -> list[ServiceResolution]:
        """``GET /service-resolutions``"""
        return await self._call(
            "settings.service_resolutions", cast_to=List[ServiceResolution], cache=True
        )

    async def assign_groups(self) -> list[AssignGroup]:
        """``GET /assign-groups``"""
        return await self._call("settings.assign_groups", cast_to=List[AssignGroup], cache=True)

    async def locations(self) -> list[Location]:
        """``GET /locations``"""
        return await self._call("settings.locations", cast_to=List[Location], cache=True)

    async def carriers(self) -> list[Carrier]:
        """``GET /carriers``"""
        return await self._call("settings.carriers", cast_to=List[Carrier], cache=True)

    async def loss_reasons(self) -> list[LossReason]:
        """``GET /loss-reasons``"""
        return await self._call("settings.loss_reasons", cast_to=List[LossReason], cache=True)

    async def custom_fields(self) -> list[CustomFieldDef]:
        """Custom field definitions. ``GET /custom-fields``"""
        return await self._call("settings.custom_fields", cast_to=List[CustomFieldDef], cache=True)

    async def csrs(self) -> CsrResponse:
        """``GET /csrs``"""
        return await self._call("settings.csrs", cast_to=CsrResponse, cache=True)

    async def tags(self) -> TagResponse:
        """``GET /tags``"""
        return await self._call("settings.tags", cast_to=TagResponse, cache=True)
