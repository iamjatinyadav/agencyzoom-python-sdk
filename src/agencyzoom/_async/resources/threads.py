"""Email and SMS conversations: ``client.email_threads`` and ``client.text_threads``."""

from __future__ import annotations

from typing import Any, Mapping

from ..._utils import build_body
from ...models import (
    DeleteMessageRequest,
    DeleteThreadRequest,
    GenericSuccessResponse,
    ProducersResponse,
    SearchMessageRequest,
    SearchMessageResponse,
    SearchSmsThreadRequest,
    SearchThreadRequest,
    SearchThreadResponse,
    UnreadThreadRequest,
    UnreadThreadResponse,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncEmailThreads", "AsyncTextThreads"]

Body = Mapping[str, Any]


class AsyncEmailThreads(AsyncAPIResource):
    """Email conversations."""

    async def search(
        self, body: SearchThreadRequest | Body | None = None, /, **filters: Any
    ) -> SearchThreadResponse:
        """``POST /email-thread/list``"""
        payload = build_body(SearchThreadRequest, body, filters)
        return await self._call("email_threads.search", body=payload, cast_to=SearchThreadResponse)

    async def get_messages(
        self, thread_id: str, body: SearchMessageRequest | Body | None = None, /, **filters: Any
    ) -> SearchMessageResponse:
        """Messages within a thread. ``POST /email-thread/email-thread-detail``"""
        payload = build_body(SearchMessageRequest, body, {**filters, "thread_id": thread_id})
        return await self._call(
            "email_threads.get_messages", body=payload, cast_to=SearchMessageResponse
        )

    async def mark_unread(self, thread_id: str, *, unread: bool = True) -> UnreadThreadResponse:
        """``POST /email-thread/unread-thread``"""
        payload = build_body(
            UnreadThreadRequest, None, {"thread_id": thread_id, "mark_unread": unread}
        )
        return await self._call(
            "email_threads.mark_unread", body=payload, cast_to=UnreadThreadResponse
        )

    async def delete(self, thread_id: str) -> GenericSuccessResponse:
        """``POST /email-thread/delete-thread``"""
        payload = build_body(DeleteThreadRequest, None, {"thread_id": thread_id})
        return await self._call(
            "email_threads.delete", body=payload, cast_to=GenericSuccessResponse
        )

    async def delete_message(self, message_id: str) -> SearchMessageResponse:
        """``POST /email-thread/delete-message``"""
        payload = build_body(DeleteMessageRequest, None, {"message_id": message_id})
        return await self._call(
            "email_threads.delete_message", body=payload, cast_to=SearchMessageResponse
        )


class AsyncTextThreads(AsyncAPIResource):
    """SMS conversations."""

    async def search(
        self, body: SearchSmsThreadRequest | Body | None = None, /, **filters: Any
    ) -> SearchThreadResponse:
        """``POST /text-thread/list``"""
        payload = build_body(SearchSmsThreadRequest, body, filters)
        return await self._call("text_threads.search", body=payload, cast_to=SearchThreadResponse)

    async def get_messages(
        self, thread_id: str, body: SearchMessageRequest | Body | None = None, /, **filters: Any
    ) -> SearchMessageResponse:
        """Messages within a thread. ``POST /text-thread/text-thread-detail``"""
        payload = build_body(SearchMessageRequest, body, {**filters, "thread_id": thread_id})
        return await self._call(
            "text_threads.get_messages", body=payload, cast_to=SearchMessageResponse
        )

    async def list_producers(self) -> ProducersResponse:
        """Producers available for SMS. ``GET /text-thread/producer``"""
        return await self._call("text_threads.list_producers", cast_to=ProducersResponse)

    async def mark_unread(self, thread_id: str, *, unread: bool = True) -> UnreadThreadResponse:
        """``POST /text-thread/unread-thread``"""
        payload = build_body(
            UnreadThreadRequest, None, {"thread_id": thread_id, "mark_unread": unread}
        )
        return await self._call(
            "text_threads.mark_unread", body=payload, cast_to=UnreadThreadResponse
        )

    async def delete(self, thread_id: str) -> GenericSuccessResponse:
        """``POST /text-thread/delete-thread``"""
        payload = build_body(DeleteThreadRequest, None, {"thread_id": thread_id})
        return await self._call("text_threads.delete", body=payload, cast_to=GenericSuccessResponse)
