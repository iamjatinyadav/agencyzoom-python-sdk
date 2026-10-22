"""Pipelines and stages: ``client.pipelines``."""

from __future__ import annotations

import builtins
from typing import List, Literal

from ...models import Pipeline, Workflow, WorkflowStage
from .._resource import AsyncAPIResource

__all__ = ["AsyncPipelines", "PipelineType"]

PipelineType = Literal["lead", "service"]


class AsyncPipelines(AsyncAPIResource):
    """Sales (``"lead"``) and service (``"service"``) pipelines."""

    async def list(self, type: PipelineType = "lead") -> list[Pipeline]:
        """``GET /pipelines``"""
        return await self._call(
            "pipelines.list", params={"type": type}, cast_to=List[Pipeline], cache=True
        )

    async def list_with_stages(self, type: PipelineType = "lead") -> builtins.list[Workflow]:
        """Pipelines including their stages. ``GET /pipelines-and-stages``"""
        return await self._call(
            "pipelines.list_with_stages",
            params={"type": type},
            cast_to=List[Workflow],
            cache=True,
        )

    async def end_stages(self, type: PipelineType = "lead") -> builtins.list[WorkflowStage]:
        """Terminal stages (won/lost/...). ``GET /end-stages``"""
        return await self._call(
            "pipelines.end_stages", params={"type": type}, cast_to=List[WorkflowStage], cache=True
        )
