"""Service center: ``client.service_tickets``."""

from __future__ import annotations

from typing import Any, AsyncIterator, List, Mapping

from ..._utils import build_body
from ...models import (
    AmsPolicy,
    GenericSuccessResponse,
    SearchServiceTicketResponse,
    SearchServiceTicketsRequest,
    ServiceTicketCompleteRequest,
    ServiceTicketCreateRequest,
    ServiceTicketDetail,
    ServiceTicketUpdateRequest,
    WrittenPolicy,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncServiceTickets"]

Body = Mapping[str, Any]


class AsyncServiceTickets(AsyncAPIResource):
    """Search, create, update and complete service tickets."""

    async def search(
        self, body: SearchServiceTicketsRequest | Body | None = None, /, **filters: Any
    ) -> SearchServiceTicketResponse:
        """Search service tickets (one page). ``POST /serviceTicket/service-tickets/list``"""
        payload = build_body(SearchServiceTicketsRequest, body, filters)
        return await self._call(
            "service_tickets.search",
            body=payload,
            cast_to=SearchServiceTicketResponse,
        )

    def paginate(
        self, body: SearchServiceTicketsRequest | Body | None = None, /, **filters: Any
    ) -> AsyncIterator[ServiceTicketDetail]:
        """Iterate over every matching service ticket, fetching pages lazily."""
        payload = build_body(SearchServiceTicketsRequest, body, filters)
        return self._paginate(
            "service_tickets.search",
            payload,
            items_key="serviceTickets",
            item_type=ServiceTicketDetail,
            page_size=100,
        )

    async def create(
        self, body: ServiceTicketCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /serviceTicket/service-tickets/create``"""
        payload = build_body(ServiceTicketCreateRequest, body, fields)
        return await self._call(
            "service_tickets.create",
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def update(
        self,
        ticket_id: int,
        body: ServiceTicketUpdateRequest | Body | None = None,
        /,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """``PUT /serviceTicket/service-tickets/{id}``"""
        payload = build_body(ServiceTicketUpdateRequest, body, fields)
        return await self._call(
            "service_tickets.update",
            path_params={"ticket_id": ticket_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def complete(
        self,
        ticket_id: int,
        *,
        resolution_id: int,
        resolution_desc: str | None = None,
        cancel_related_tasks: bool | None = None,
    ) -> GenericSuccessResponse:
        """``POST /serviceTicket/service-tickets/{id}/complete``"""
        fields: dict[str, Any] = {"id": ticket_id, "resolution_id": resolution_id}
        if resolution_desc is not None:
            fields["resolution_desc"] = resolution_desc
        if cancel_related_tasks is not None:
            fields["cancel_related_tasks"] = cancel_related_tasks
        payload = build_body(ServiceTicketCompleteRequest, None, fields)
        return await self._call(
            "service_tickets.complete",
            path_params={"ticket_id": ticket_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def list_policies(self, ticket_id: int) -> list[WrittenPolicy]:
        """``GET /serviceTicket/service-tickets/{id}/policies``"""
        return await self._call(
            "service_tickets.list_policies",
            path_params={"ticket_id": ticket_id},
            cast_to=List[WrittenPolicy],
        )

    async def list_ams_policies(self, ticket_id: int) -> list[AmsPolicy]:
        """``GET /serviceTicket/service-tickets/{id}/ams-policies``"""
        return await self._call(
            "service_tickets.list_ams_policies",
            path_params={"ticket_id": ticket_id},
            cast_to=List[AmsPolicy],
        )
