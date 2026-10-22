"""Task management: ``client.tasks``."""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterable, Mapping

from ..._utils import build_body
from ...models import (
    GenericSuccessResponse,
    Task,
    TaskBatchDeleteRequest,
    TaskCreateRequest,
    TaskReopenRequest,
    TaskSearchRequest,
    TaskSearchResponse,
    TaskUpdateRequest,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncTasks"]

Body = Mapping[str, Any]


class AsyncTasks(AsyncAPIResource):
    """Search, create, update, complete and reopen tasks."""

    async def search(
        self, body: TaskSearchRequest | Body | None = None, /, **filters: Any
    ) -> TaskSearchResponse:
        """Search tasks (one page). ``POST /tasks/list``"""
        payload = build_body(TaskSearchRequest, body, filters)
        return await self._call("tasks.search", body=payload, cast_to=TaskSearchResponse)

    def paginate(
        self, body: TaskSearchRequest | Body | None = None, /, **filters: Any
    ) -> AsyncIterator[Task]:
        """Iterate over every matching task, fetching pages lazily."""
        payload = build_body(TaskSearchRequest, body, filters)
        return self._paginate(
            "tasks.search", payload, items_key="tasks", item_type=Task, page_size=200
        )

    async def get(self, task_id: int) -> Task:
        """``GET /tasks/{taskId}``"""
        return await self._call("tasks.get", path_params={"task_id": task_id}, cast_to=Task)

    async def create(
        self, body: TaskCreateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``POST /tasks``"""
        payload = build_body(TaskCreateRequest, body, fields)
        return await self._call("tasks.create", body=payload, cast_to=GenericSuccessResponse)

    async def update(
        self, task_id: int, body: TaskUpdateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``PUT /tasks/{taskId}``"""
        payload = build_body(TaskUpdateRequest, body, fields)
        return await self._call(
            "tasks.update",
            path_params={"task_id": task_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def delete(self, task_id: int) -> GenericSuccessResponse:
        """``DELETE /tasks/{taskId}``"""
        return await self._call(
            "tasks.delete", path_params={"task_id": task_id}, cast_to=GenericSuccessResponse
        )

    async def batch_delete(self, task_ids: Iterable[int]) -> GenericSuccessResponse:
        """``POST /tasks/batch-delete``"""
        payload = build_body(TaskBatchDeleteRequest, None, {"task_ids": list(task_ids)})
        return await self._call("tasks.batch_delete", body=payload, cast_to=GenericSuccessResponse)

    async def complete(self, task_id: int) -> GenericSuccessResponse:
        """``PUT /tasks/{taskId}/completed``"""
        return await self._call(
            "tasks.complete", path_params={"task_id": task_id}, cast_to=GenericSuccessResponse
        )

    async def reopen(self, task_id: int, *, comments: str | None = None) -> GenericSuccessResponse:
        """``PUT /tasks/{taskId}/reopened``"""
        fields = {} if comments is None else {"comments": comments}
        payload = build_body(TaskReopenRequest, None, fields)
        return await self._call(
            "tasks.reopen",
            path_params={"task_id": task_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )
