"""The endpoint registry must match the OpenAPI spec, the resource code, and the public API."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from agencyzoom import ENDPOINTS, AgencyZoom
from agencyzoom._endpoints import placeholders

from .conftest import make_jwt

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi" / "agencyzoom.yaml"
RESOURCES = ROOT / "src" / "agencyzoom" / "_async" / "resources"
SPEC_ROOT = "/v1/api"


def normalise(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


requires_spec = pytest.mark.skipif(
    not SPEC.exists(),
    reason="openapi/agencyzoom.yaml is not committed; run `make spec` to download it",
)


def spec_operations() -> set[tuple[str, str]]:
    spec = yaml.safe_load(SPEC.read_text("utf-8"))
    return {
        (method.upper(), normalise(path))
        for path, ops in spec["paths"].items()
        for method in ops
        if method in {"get", "post", "put", "delete", "patch"}
    }


def registry_operations() -> set[tuple[str, str]]:
    return {(e.method, normalise(SPEC_ROOT + e.path)) for e in ENDPOINTS.values()}


def resource_calls() -> list[tuple[str, set[str] | None]]:
    """(endpoint_id, path_param_names) for every `_call`/`_paginate` in the resources."""
    calls: list[tuple[str, set[str] | None]] = []
    for file in [*RESOURCES.glob("*.py"), RESOURCES.parent / "_auth.py"]:
        tree = ast.parse(file.read_text("utf-8"))
        constants = {
            n.targets[0].id: n.value.value
            for n in tree.body
            if isinstance(n, ast.Assign)
            and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        }
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"_call", "_paginate", "authenticate", "_send_json"}
            ):
                continue
            first = node.args[0]
            endpoint_id = (
                first.value
                if isinstance(first, ast.Constant)
                else constants.get(first.id)
                if isinstance(first, ast.Name)
                else None
            )
            if endpoint_id is None:
                continue  # automatic login selects the session's configured login endpoint
            params: set[str] | None = set()
            for kw in node.keywords:
                if kw.arg == "path_params":
                    params = (
                        {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
                        if isinstance(kw.value, ast.Dict)
                        else None  # computed dynamically; can't check statically
                    )
            calls.append((endpoint_id, params))
    return calls


@requires_spec
def test_registry_matches_the_spec_exactly() -> None:
    spec, registry = spec_operations(), registry_operations()
    assert not spec - registry, (
        f"Spec endpoints missing from the registry: {sorted(spec - registry)}"
    )
    assert not registry - spec, f"Registry endpoints not in the spec: {sorted(registry - spec)}"
    assert len(ENDPOINTS) == len(spec) == 117


def test_every_registered_endpoint_is_used_and_every_used_one_is_registered() -> None:
    used = {endpoint_id for endpoint_id, _ in resource_calls()}
    assert not set(ENDPOINTS) - used, f"Unused endpoints: {sorted(set(ENDPOINTS) - used)}"
    assert not used - set(ENDPOINTS), f"Unknown endpoint IDs: {sorted(used - set(ENDPOINTS))}"


def test_path_params_match_placeholders() -> None:
    for endpoint_id, params in resource_calls():
        if params is None:
            continue
        expected = set(placeholders(ENDPOINTS[endpoint_id].path))
        assert params == expected, f"{endpoint_id}: passes {params}, path needs {expected}"


@pytest.mark.parametrize("endpoint_id", sorted(ENDPOINTS))
def test_endpoint_ids_mirror_the_public_api(endpoint_id: str) -> None:
    """`"leads.notes.create"` must be reachable as `client.leads.notes.create`."""
    with AgencyZoom(token=make_jwt()) as client:
        target: object = client
        for part in endpoint_id.split("."):
            assert hasattr(target, part), f"client.{endpoint_id} does not exist"
            target = getattr(target, part)
        assert callable(target)
