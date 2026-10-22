"""Opportunity management: ``client.opportunities`` (with drivers and vehicles)."""

from __future__ import annotations

from functools import cached_property
from typing import Any, List, Mapping

from ..._utils import build_body
from ...models import (
    CreateDriverRequest,
    CreateOpportunityRequest,
    DriverRequest,
    GenericSuccessResponse,
    GetDriverDto,
    GetVehicleDto,
    Opportunity,
    UpdateOpportunityRequest,
    VehicleRequest,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncDrivers", "AsyncOpportunities", "AsyncVehicles"]

Body = Mapping[str, Any]


class AsyncOpportunities(AsyncAPIResource):
    """Opportunities (lines of business on a lead), their drivers and vehicles."""

    @cached_property
    def drivers(self) -> AsyncDrivers:
        return AsyncDrivers(self._http)

    @cached_property
    def vehicles(self) -> AsyncVehicles:
        return AsyncVehicles(self._http)

    async def get(self, opportunity_id: int) -> Opportunity:
        """``GET /opportunities/{opportunityId}``"""
        return await self._call(
            "opportunities.get", path_params={"opportunity_id": opportunity_id}, cast_to=Opportunity
        )

    async def create(
        self, body: CreateOpportunityRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /opportunities``"""
        payload = build_body(CreateOpportunityRequest, body, fields)
        return await self._call(
            "opportunities.create", body=payload, cast_to=GenericSuccessResponse
        )

    async def update(
        self,
        opportunity_id: int,
        body: UpdateOpportunityRequest | Body | None = None,
        /,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """``PUT /opportunities/{opportunityId}``"""
        payload = build_body(UpdateOpportunityRequest, body, fields)
        return await self._call(
            "opportunities.update",
            path_params={"opportunity_id": opportunity_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, opportunity_id: int) -> GenericSuccessResponse:
        """``DELETE /opportunities/{opportunityId}``"""
        return await self._call(
            "opportunities.delete",
            path_params={"opportunity_id": opportunity_id},
            cast_to=GenericSuccessResponse,
        )


class AsyncDrivers(AsyncAPIResource):
    """``client.opportunities.drivers``"""

    async def list(self, opportunity_id: int) -> list[GetDriverDto]:
        """``GET /opportunities/{opportunityId}/drivers``"""
        return await self._call(
            "opportunities.drivers.list",
            path_params={"opportunity_id": opportunity_id},
            cast_to=List[GetDriverDto],
        )

    async def get(self, driver_id: int) -> GetDriverDto:
        """``GET /opportunities/drivers/{driverId}``"""
        return await self._call(
            "opportunities.drivers.get", path_params={"driver_id": driver_id}, cast_to=GetDriverDto
        )

    async def create(
        self, opportunity_id: int, body: CreateDriverRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /opportunities/{opportunityId}/driver``"""
        payload = build_body(CreateDriverRequest, body, fields)
        return await self._call(
            "opportunities.drivers.create",
            path_params={"opportunity_id": opportunity_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def update(
        self, driver_id: int, body: DriverRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``PUT /opportunities/drivers/{driverId}``"""
        payload = build_body(DriverRequest, body, fields)
        return await self._call(
            "opportunities.drivers.update",
            path_params={"driver_id": driver_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, driver_id: int) -> GenericSuccessResponse:
        """``DELETE /opportunities/drivers/{driverId}``"""
        return await self._call(
            "opportunities.drivers.delete",
            path_params={"driver_id": driver_id},
            cast_to=GenericSuccessResponse,
        )

    async def link(self, opportunity_id: int, driver_id: int) -> GenericSuccessResponse:
        """``PUT /opportunities/{opportunityId}/link-driver/{driverId}``"""
        return await self._call(
            "opportunities.drivers.link",
            path_params={"opportunity_id": opportunity_id, "driver_id": driver_id},
            cast_to=GenericSuccessResponse,
        )

    async def unlink(self, opportunity_id: int, driver_id: int) -> GenericSuccessResponse:
        """``PUT /opportunities/{opportunityId}/unlink-driver/{driverId}``"""
        return await self._call(
            "opportunities.drivers.unlink",
            path_params={"opportunity_id": opportunity_id, "driver_id": driver_id},
            cast_to=GenericSuccessResponse,
        )


class AsyncVehicles(AsyncAPIResource):
    """``client.opportunities.vehicles``"""

    async def list(self, opportunity_id: int) -> list[GetVehicleDto]:
        """``GET /opportunities/{opportunityId}/vehicles``"""
        return await self._call(
            "opportunities.vehicles.list",
            path_params={"opportunity_id": opportunity_id},
            cast_to=List[GetVehicleDto],
        )

    async def get(self, vehicle_id: int) -> GetVehicleDto:
        """``GET /opportunities/vehicles/{vehicleId}``"""
        return await self._call(
            "opportunities.vehicles.get",
            path_params={"vehicle_id": vehicle_id},
            cast_to=GetVehicleDto,
        )

    async def create(
        self, opportunity_id: int, body: VehicleRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /opportunities/{opportunityId}/vehicle``"""
        payload = build_body(VehicleRequest, body, fields)
        return await self._call(
            "opportunities.vehicles.create",
            path_params={"opportunity_id": opportunity_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def update(
        self, vehicle_id: int, body: VehicleRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``PUT /opportunities/vehicles/{vehicleId}``"""
        payload = build_body(VehicleRequest, body, fields)
        return await self._call(
            "opportunities.vehicles.update",
            path_params={"vehicle_id": vehicle_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, vehicle_id: int) -> GenericSuccessResponse:
        """``DELETE /opportunities/vehicles/{vehicleId}``"""
        return await self._call(
            "opportunities.vehicles.delete",
            path_params={"vehicle_id": vehicle_id},
            cast_to=GenericSuccessResponse,
        )

    async def link(self, opportunity_id: int, vehicle_id: int) -> GenericSuccessResponse:
        """``PUT /opportunities/{opportunityId}/link-vehicle/{vehicleId}``"""
        return await self._call(
            "opportunities.vehicles.link",
            path_params={"opportunity_id": opportunity_id, "vehicle_id": vehicle_id},
            cast_to=GenericSuccessResponse,
        )

    async def unlink(self, opportunity_id: int, vehicle_id: int) -> GenericSuccessResponse:
        """``PUT /opportunities/{opportunityId}/unlink-vehicle/{vehicleId}``"""
        return await self._call(
            "opportunities.vehicles.unlink",
            path_params={"opportunity_id": opportunity_id, "vehicle_id": vehicle_id},
            cast_to=GenericSuccessResponse,
        )
