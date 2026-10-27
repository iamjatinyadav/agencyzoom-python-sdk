"""Exercise every public endpoint against its wire contract in the local OpenAPI spec.

The proprietary spec remains uncommitted. CI's spec workflow downloads it before
running these checks; an installation without the spec skips this module.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest
import respx

from agencyzoom import ENDPOINTS, AgencyZoom, AsyncAgencyZoom
from agencyzoom.models import AgencyZoomModel

from .conftest import BASE_URL

yaml = pytest.importorskip("yaml")
SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi" / "agencyzoom.yaml"
pytestmark = pytest.mark.skipif(
    not SPEC_PATH.exists(), reason="run make spec for endpoint contracts"
)


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text("utf-8"))


def shape(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    result = dict(schema)
    if "allOf" in schema:
        props, required = {}, []
        for part in schema["allOf"]:
            resolved = shape(part, spec)
            props.update(resolved.get("properties", {}))
            required.extend(resolved.get("required", []))
        props.update(schema.get("properties", {}))
        required.extend(schema.get("required", []))
        result.update(type="object", properties=props, required=required)
    return result


def sample(schema: dict[str, Any], spec: dict[str, Any], depth: int = 0) -> Any:
    schema = shape(schema, spec)
    kind = schema.get("type", "object")
    if schema.get("enum"):
        return schema["enum"][0]
    if kind == "integer":
        return 42
    if kind == "number":
        return 1.25
    if kind == "boolean":
        return True
    if kind in {"string", "varchar"}:
        return "2026-01-01" if schema.get("format") == "date" else "sample"
    if kind == "array":
        return [] if depth > 6 else [sample(schema.get("items", {}), spec, depth + 1)]
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    return {
        name: sample(prop or {}, spec, depth + 1)
        for name, prop in properties.items()
        if name in required
        or (
            depth < 2
            and shape(prop or {}, spec).get("type")
            in {"integer", "number", "boolean", "string", "varchar"}
        )
    }


def normalise(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def contract(endpoint_id: str, spec: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    endpoint = ENDPOINTS[endpoint_id]
    matching = [
        (path, operation)
        for path, operations in spec["paths"].items()
        for method, operation in operations.items()
        if method.upper() == endpoint.method
        and normalise(path) == normalise("/v1/api" + endpoint.path)
    ]
    assert len(matching) == 1
    path, operation = matching[0]
    return endpoint.method, re.sub(r"\{[^}]+\}", "42", path), operation


def prepare_call(
    client: Any, endpoint_id: str, operation: dict[str, Any], spec: dict[str, Any]
) -> tuple[Any, list[Any], dict[str, Any], Any]:
    target = client
    for part in endpoint_id.split("."):
        target = getattr(target, part)
    schema = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    payload = sample(schema, spec) if schema else None
    properties = shape(schema, spec).get("properties", {}) if schema else {}
    aliases = {name.replace("_", "").lower(): name for name in properties}
    args, kwargs = [], {}
    has_body = "body" in inspect.signature(target).parameters
    expected_body = payload if has_body else {}
    for name, parameter in inspect.signature(target).parameters.items():
        if parameter.kind in {inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL}:
            continue
        if name == "body":
            value = payload
        elif name == "files":
            value = ("sample.txt", b"sample")
        elif name == "api_token":
            continue  # configured on the client
        elif name in {"username", "password", "refresh_token", "code"}:
            value = "sample"
            key = aliases.get(name.replace("_", "").lower())
            if key:
                expected_body[key] = value
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            key = aliases.get(name.replace("_", "").lower())
            value = sample(properties[key], spec) if key else 42
            if key and not has_body:
                expected_body[key] = value
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[name] = value
    if endpoint_id in {"auth.login", "auth.sso_login", "v4sso.login"}:
        expected_body["version"] = 2
    if endpoint_id == "service_tickets.complete":
        expected_body["id"] = 42
    if endpoint_id == "leads.files.rename":
        expected_body["customerReferralId"] = 42
    if endpoint_id in {"email_threads.mark_unread", "text_threads.mark_unread"}:
        expected_body["markUnread"] = True
    return target, args, kwargs, expected_body


def response_body(endpoint_id: str, operation: dict[str, Any], spec: dict[str, Any]) -> Any:
    if endpoint_id in {"auth.login", "auth.sso_login", "auth.refresh", "v4sso.login"}:
        return {"jwt": "response-token", "refreshToken": "response-refresh", "expiresIn": 3600}
    response = operation["responses"].get("200", operation["responses"].get(200, {}))
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    return sample(schema, spec)


def assert_request(
    route: respx.Route, endpoint_id: str, operation: dict[str, Any], expected_body: Any
) -> None:
    assert route.call_count == 1
    request = route.calls[0].request
    if endpoint_id == "leads.files.upload":
        assert b'name="entityId"' in request.content
        assert b"42" in request.content
        assert b'filename="sample.txt"' in request.content
    elif "requestBody" in operation and "application/json" in operation["requestBody"].get(
        "content", {}
    ):
        assert json.loads(request.content) == expected_body
    if endpoint_id == "policies.create":
        assert request.headers["X-Api-Token"] == "sample-api-token"
    for parameter in operation.get("parameters", []):
        if parameter.get("in") == "query" and parameter["name"] == "type":
            assert request.url.params["type"] == "lead"
    if not endpoint_id.startswith(("auth.", "v4sso.")) or endpoint_id == "auth.logout":
        assert request.headers["Authorization"] == "Bearer sample-token"


@pytest.mark.parametrize("endpoint_id", sorted(ENDPOINTS))
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_public_endpoint_wire_contract(
    api: respx.MockRouter, spec: dict[str, Any], endpoint_id: str, mode: str
) -> None:
    method, path, operation = contract(endpoint_id, spec)
    response = response_body(endpoint_id, operation, spec)
    route = api.route(method=method, path=path).respond(200, json=response)
    client_type = AgencyZoom if mode == "sync" else AsyncAgencyZoom
    client = client_type(
        "sample",
        "sample",
        token="sample-token",
        refresh_token="sample",
        api_token="sample-api-token",
        base_url=BASE_URL,
        rate_limit_per_minute=None,
        strict_response_validation=True,
    )
    try:
        target, args, kwargs, expected_body = prepare_call(client, endpoint_id, operation, spec)
        result = target(*args, **kwargs)
        if mode == "async":
            result = await result
        assert result is None or isinstance(result, (AgencyZoomModel, list))
        if isinstance(result, list):
            assert all(isinstance(item, AgencyZoomModel) for item in result)
        assert_request(route, endpoint_id, operation, expected_body)
    finally:
        if mode == "async":
            await client.close()
        else:
            client.close()
