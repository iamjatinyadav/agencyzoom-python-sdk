"""Lead management: ``client.leads``."""

from __future__ import annotations

import builtins
from functools import cached_property
from typing import Any, AsyncIterator, List, Mapping, Sequence

from ..._utils import FileInput, build_body, prepare_files
from ...models import (
    BatchLeadDataRequest,
    BizLeadDataRequest,
    BizLeadUpdateRequest,
    File,
    GenericSuccessResponse,
    Lead,
    LeadChangeStatusRequest,
    LeadCreateRequest,
    LeadDeleteRequest,
    LeadDetail,
    LeadFilesRequest,
    LeadOpportunityCreateRequest,
    LeadOpportunityUpdateRequest,
    LeadQuoteCreateRequest,
    LeadQuoteUpdateRequest,
    LeadsCountResponse,
    LeadSearchRequest,
    LeadSearchResponse,
    LeadSoldRequest,
    LeadSoldResponse,
    LeadUpdateRequest,
    Note,
    NoteRequest,
    Opportunity,
    Quote,
    RecycleEvents,
    RenameLeadFileRequest,
    Task,
)
from .._compat import run_blocking
from .._resource import AsyncAPIResource

__all__ = [
    "AsyncLeadFiles",
    "AsyncLeadNotes",
    "AsyncLeadOpportunities",
    "AsyncLeadQuotes",
    "AsyncLeads",
]

Body = Mapping[str, Any]


class AsyncLeads(AsyncAPIResource):
    """Search, create and manage leads (personal and commercial)."""

    @cached_property
    def notes(self) -> AsyncLeadNotes:
        return AsyncLeadNotes(self._http)

    @cached_property
    def quotes(self) -> AsyncLeadQuotes:
        return AsyncLeadQuotes(self._http)

    @cached_property
    def files(self) -> AsyncLeadFiles:
        return AsyncLeadFiles(self._http)

    @cached_property
    def opportunities(self) -> AsyncLeadOpportunities:
        return AsyncLeadOpportunities(self._http)

    # --------------------------------------------------------------- search

    async def search(
        self, body: LeadSearchRequest | Body | None = None, /, **filters: Any
    ) -> LeadSearchResponse:
        """Search leads (one page). ``POST /leads/list``"""
        payload = build_body(LeadSearchRequest, body, filters)
        return await self._call("leads.search", body=payload, cast_to=LeadSearchResponse)

    def paginate(
        self, body: LeadSearchRequest | Body | None = None, /, **filters: Any
    ) -> AsyncIterator[Lead]:
        """Iterate over every lead matching the filters, fetching pages lazily."""
        payload = build_body(LeadSearchRequest, body, filters)
        return self._paginate(
            "leads.search", payload, items_key="leads", item_type=Lead, page_size=100
        )

    async def count(
        self, body: LeadSearchRequest | Body | None = None, /, **filters: Any
    ) -> LeadsCountResponse:
        """Count leads per pipeline/stage. ``POST /leads/pipeline-count``"""
        payload = build_body(LeadSearchRequest, body, filters)
        return await self._call("leads.count", body=payload, cast_to=LeadsCountResponse)

    # --------------------------------------------------------------- CRUD

    async def get(self, lead_id: int) -> LeadDetail:
        """Get lead details. ``GET /leads/{leadId}``"""
        return await self._call("leads.get", path_params={"lead_id": lead_id}, cast_to=LeadDetail)

    async def create(
        self, body: LeadCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create a personal lead. ``POST /leads/create``"""
        payload = build_body(LeadCreateRequest, body, fields)
        return await self._call("leads.create", body=payload, cast_to=GenericSuccessResponse)

    async def batch_create(
        self, body: BatchLeadDataRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create many leads in one call. ``POST /leads/batch-create``"""
        payload = build_body(BatchLeadDataRequest, body, fields)
        return await self._call("leads.batch_create", body=payload, cast_to=GenericSuccessResponse)

    async def update(
        self, lead_id: int, body: LeadUpdateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Update a lead. ``PUT /leads/{leadId}``"""
        payload = build_body(LeadUpdateRequest, body, fields)
        return await self._call(
            "leads.update",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(
        self, lead_id: int, *, delete_contact: bool | None = None
    ) -> GenericSuccessResponse:
        """Delete a lead. ``POST /leads/{leadId}/delete-lead``"""
        fields = {} if delete_contact is None else {"delete_contact": delete_contact}
        payload = build_body(LeadDeleteRequest, None, fields)
        return await self._call(
            "leads.delete",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    # --------------------------------------------------------------- commercial

    async def create_commercial(
        self, body: BizLeadDataRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create a commercial (business) lead. ``POST /leads/create-biz-lead``"""
        payload = build_body(BizLeadDataRequest, body, fields)
        return await self._call(
            "leads.create_commercial", body=payload, cast_to=GenericSuccessResponse
        )

    async def update_commercial(
        self, lead_id: int, body: BizLeadUpdateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Update a commercial lead. ``PUT /leads/{leadId}/update-biz-lead``"""
        payload = build_body(BizLeadUpdateRequest, body, fields)
        return await self._call(
            "leads.update_commercial",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    # --------------------------------------------------------------- workflow

    async def change_status(
        self, lead_id: int, body: LeadChangeStatusRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Change a lead's status (e.g. lost, X-dated). ``PUT /leads/{leadId}/status``"""
        payload = build_body(LeadChangeStatusRequest, body, fields)
        return await self._call(
            "leads.change_status",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def change_stage(
        self, lead_id: int, body: LeadChangeStatusRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Move a lead to another pipeline stage. ``PUT /leads/{leadId}/stage``"""
        payload = build_body(LeadChangeStatusRequest, body, fields)
        return await self._call(
            "leads.change_stage",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def mark_sold(
        self, lead_id: int, body: LeadSoldRequest | Body | None = None, /, **fields: Any
    ) -> LeadSoldResponse:
        """Move a lead to sold. ``POST /leads/{leadId}/sold``"""
        payload = build_body(LeadSoldRequest, body, fields)
        return await self._call(
            "leads.mark_sold",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=LeadSoldResponse,
        )

    async def list_tasks(self, lead_id: int) -> list[Task]:
        """Tasks attached to a lead. ``GET /leads/{leadId}/tasks``"""
        return await self._call(
            "leads.list_tasks", path_params={"lead_id": lead_id}, cast_to=List[Task]
        )

    async def recycle_events(self, lead_id: int) -> RecycleEvents:
        """X-date recycle events for a lead. ``GET /{leadId}/recycle-events``"""
        return await self._call(
            "leads.recycle_events", path_params={"lead_id": lead_id}, cast_to=RecycleEvents
        )


class AsyncLeadNotes(AsyncAPIResource):
    """``client.leads.notes``"""

    async def list(self, lead_id: int) -> list[Note]:
        """``GET /leads/{leadId}/notes``"""
        return await self._call(
            "leads.notes.list", path_params={"lead_id": lead_id}, cast_to=List[Note]
        )

    async def create(self, lead_id: int, note: str) -> GenericSuccessResponse:
        """``POST /leads/{leadId}/notes``"""
        payload = build_body(NoteRequest, None, {"note": note})
        return await self._call(
            "leads.notes.create",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )


class AsyncLeadQuotes(AsyncAPIResource):
    """``client.leads.quotes``"""

    async def list(self, lead_id: int) -> list[Quote]:
        """``GET /leads/{leadId}/quotes``"""
        return await self._call(
            "leads.quotes.list", path_params={"lead_id": lead_id}, cast_to=List[Quote]
        )

    async def create(
        self, lead_id: int, body: LeadQuoteCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /leads/{leadId}/quotes``"""
        payload = build_body(LeadQuoteCreateRequest, body, fields)
        return await self._call(
            "leads.quotes.create",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def update(
        self, lead_id: int, body: LeadQuoteUpdateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Update a quote; the quote ``id`` goes in the body. ``PUT /leads/{leadId}/quotes``"""
        payload = build_body(LeadQuoteUpdateRequest, body, fields)
        return await self._call(
            "leads.quotes.update",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, lead_id: int, quote_id: int) -> GenericSuccessResponse:
        """``DELETE /leads/{leadId}/quotes/{quoteId}``"""
        return await self._call(
            "leads.quotes.delete",
            path_params={"lead_id": lead_id, "quote_id": quote_id},
            cast_to=GenericSuccessResponse,
        )


class AsyncLeadOpportunities(AsyncAPIResource):
    """``client.leads.opportunities``"""

    async def list(self, lead_id: int) -> list[Opportunity]:
        """``GET /leads/{leadId}/opportunities``"""
        return await self._call(
            "leads.opportunities.list", path_params={"lead_id": lead_id}, cast_to=List[Opportunity]
        )

    async def create(
        self,
        lead_id: int,
        body: LeadOpportunityCreateRequest | Body | None = None,
        /,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """``POST /leads/{leadId}/opportunities``"""
        payload = build_body(LeadOpportunityCreateRequest, body, fields)
        return await self._call(
            "leads.opportunities.create",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def update(
        self,
        lead_id: int,
        body: LeadOpportunityUpdateRequest | Body | None = None,
        /,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Update an opportunity; its ``id`` goes in the body. ``PUT /leads/{leadId}/opportunities``"""
        payload = build_body(LeadOpportunityUpdateRequest, body, fields)
        return await self._call(
            "leads.opportunities.update",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, lead_id: int, opportunity_id: int) -> GenericSuccessResponse:
        """``DELETE /leads/{leadId}/opportunities/{opportunityId}``"""
        return await self._call(
            "leads.opportunities.delete",
            path_params={"lead_id": lead_id, "opportunity_id": opportunity_id},
            cast_to=GenericSuccessResponse,
        )


class AsyncLeadFiles(AsyncAPIResource):
    """``client.leads.files``"""

    async def list(
        self, body: LeadFilesRequest | Body | None = None, /, **filters: Any
    ) -> list[File]:
        """List files for a lead (pass ``customer_referral_id``). ``POST /leads/files``"""
        payload = build_body(LeadFilesRequest, body, filters)
        return await self._call("leads.files.list", body=payload, cast_to=List[File])

    async def upload(
        self, lead_id: int, files: FileInput | Sequence[FileInput]
    ) -> builtins.list[File]:
        """Upload one or more files to a lead. ``POST /leads/upload-file``

        ``files`` may be paths, bytes, open binary files, or ``(name, content[, type])`` tuples.
        """
        parts = await run_blocking(prepare_files, files)
        return await self._call(
            "leads.files.upload",
            data={"entityId": str(lead_id)},
            files=parts,
            cast_to=List[File],
        )

    async def rename(
        self, lead_id: int, file_id: int, new_file_name: str
    ) -> GenericSuccessResponse:
        """``PUT /leads/{leadId}/rename``"""
        payload = build_body(
            RenameLeadFileRequest,
            None,
            {"customer_referral_id": lead_id, "file_id": file_id, "new_file_name": new_file_name},
        )
        return await self._call(
            "leads.files.rename",
            path_params={"lead_id": lead_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, lead_id: int, file_id: int) -> GenericSuccessResponse:
        """``DELETE /leads/{leadId}/files/{fileId}``"""
        return await self._call(
            "leads.files.delete",
            path_params={"lead_id": lead_id, "file_id": file_id},
            cast_to=GenericSuccessResponse,
        )
