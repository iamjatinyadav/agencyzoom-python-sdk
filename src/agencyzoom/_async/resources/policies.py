"""Policy management: ``client.policies``."""

from __future__ import annotations

from typing import Any, Mapping

from ..._exceptions import ConfigurationError
from ..._utils import build_body
from ...models import (
    EnterprisePolicyCreateRequest,
    EnterprisePolicyUpdateStatusRequest,
    GenericSuccessResponse,
    PolicyEndorseRequest,
    PolicyUpdateRequest,
    TagPolicyDataRequest,
)
from .._resource import AsyncAPIResource

__all__ = ["AsyncPolicies"]

Body = Mapping[str, Any]


class AsyncPolicies(AsyncAPIResource):
    """Create, update, tag and endorse policies."""

    async def create(
        self,
        body: EnterprisePolicyCreateRequest | Body | None = None,
        /,
        *,
        api_token: str | None = None,
        **fields: Any,
    ) -> GenericSuccessResponse:
        """Create a policy. ``POST /policies/create``

        This endpoint additionally requires an ``X-Api-Token`` header: pass
        ``api_token`` here, to the client, or set ``AGENCYZOOM_API_TOKEN``.
        """
        token = api_token or self._http.options.api_token
        if not token:
            raise ConfigurationError(
                "policies.create requires an API token: pass `api_token=` or set AGENCYZOOM_API_TOKEN."
            )
        payload = build_body(EnterprisePolicyCreateRequest, body, fields)
        return await self._call(
            "policies.create",
            body=payload,
            headers={"X-Api-Token": token},
            cast_to=GenericSuccessResponse,
        )

    async def update(
        self, policy_id: int, body: PolicyUpdateRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """``PUT /policies/{policyId}``"""
        payload = build_body(PolicyUpdateRequest, body, fields)
        return await self._call(
            "policies.update",
            path_params={"policy_id": policy_id},
            body=payload,
            cast_to=GenericSuccessResponse,
        )

    async def update_tags(
        self, body: TagPolicyDataRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Replace a policy's tags (``tag_names`` is comma-separated). ``POST /policies/update-tags``"""
        payload = build_body(TagPolicyDataRequest, body, fields)
        return await self._call(
            "policies.update_tags", body=payload, cast_to=GenericSuccessResponse
        )

    async def update_status(self, policy_id: int, status: int) -> GenericSuccessResponse:
        """``POST /policies/update-status``"""
        payload = build_body(
            EnterprisePolicyUpdateStatusRequest, None, {"policy_id": policy_id, "status": status}
        )
        return await self._call(
            "policies.update_status", body=payload, cast_to=GenericSuccessResponse
        )

    async def endorse(
        self, body: PolicyEndorseRequest | Body | None = None, /, **fields: Any
    ) -> GenericSuccessResponse:
        """Create an endorsement. ``POST /policies/endorse``"""
        payload = build_body(PolicyEndorseRequest, body, fields)
        return await self._call("policies.endorse", body=payload, cast_to=GenericSuccessResponse)
