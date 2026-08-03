"""Transport-neutral semantic contract for the public FreeCAD RPC surface."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import Draft202012Validator

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "freecad_rpc_contract_snapshot.json"
_JSON_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
_PARAMETER_SCHEMAS: dict[str, dict] = {
    "attachment_offset": {"type": ["null", "object"]},
    "client_monotonic_ns": {"type": "integer"},
    "constraint_indices": {"type": ["array", "null"]},
    "constraint_names": {"type": ["array", "null"]},
    "credential": {"type": "object"},
    "destination": {"type": "string"},
    "doc_name": {"type": "string"},
    "expected_destination_sha256": {"type": "string"},
    "index": {"type": ["integer", "null"]},
    "leases": {"type": "array"},
    "name": {"type": ["null", "string"]},
    "nonce": {"type": ["integer", "string"]},
    "obj_name": {"type": "string"},
    "object_name": {"type": ["null", "string"]},
    "overwrite": {"type": "boolean"},
    "payload": {"type": "object"},
    "progress_detail": {"type": "string"},
    "relative_path": {"type": "string"},
    "request_id": {"type": "string"},
    "save_mode": {"enum": ["discard", "save", "save_as"], "type": "string"},
    "selector": {"type": ["null", "object"]},
    "support": {"type": ["array", "null", "object", "string"]},
    "target_request_id": {"type": "string"},
    "task_description": {"type": "string"},
    "validation_profile": {"type": "string"},
    "value": {"type": ["integer", "number", "string"]},
}


def _load_snapshot() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _annotation_text(annotation: object) -> str:
    if annotation is inspect.Signature.empty:
        return ""
    text = str(annotation).replace("typing.", "")
    while len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return text


def _direct_schema(annotation: object, default: object) -> dict | None:
    schema_type = {
        bool: "boolean",
        dict: "object",
        float: "number",
        int: "integer",
        list: "array",
        str: "string",
        tuple: "array",
    }.get(annotation)
    if schema_type is None:
        return None
    types = {schema_type, "null"} if default is None else {schema_type}
    return {"type": schema_type if len(types) == 1 else sorted(types)}


def _schema_type_from_text(lowered: str, default: object) -> str | None:
    if lowered.startswith(("dict", "mapping")):
        return "object"
    if lowered.startswith(("list", "sequence", "tuple", "set", "frozenset")):
        return "array"
    prefixes = {
        "bool": "boolean",
        "int": "integer",
        "float": "number",
        "str": "string",
    }
    for prefix, schema_type in prefixes.items():
        if lowered.startswith(prefix):
            return schema_type
    if default is inspect.Signature.empty or default is None:
        return None
    return {
        bool: "boolean",
        int: "integer",
        float: "number",
        str: "string",
        list: "array",
        tuple: "array",
        dict: "object",
    }.get(type(default))


def _wire_schema(
    annotation: object,
    *,
    default: object = inspect.Signature.empty,
    parameter_name: str = "",
) -> dict:
    """Map a Python boundary annotation to an encoding-independent JSON schema."""

    if annotation is inspect.Signature.empty and parameter_name in _PARAMETER_SCHEMAS:
        return _PARAMETER_SCHEMAS[parameter_name]
    direct_schema = _direct_schema(annotation, default)
    if direct_schema is not None:
        return direct_schema
    lowered = _annotation_text(annotation).lower().replace(" ", "")
    schema_type = _schema_type_from_text(lowered, default)
    if schema_type is None:
        return {}
    types = {schema_type}
    if default is None or "|none" in lowered or "optional[" in lowered:
        types.add("null")
    if len(types) == 1:
        return {"type": schema_type}
    return {"type": sorted(types)}


def _json_default(value: object) -> object:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


def _capture_parameters(method: object) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for parameter in inspect.signature(method).parameters.values():
        if parameter.name == "self":
            continue
        item: dict[str, Any] = {
            "name": parameter.name,
            "kind": parameter.kind.name.lower(),
            "required": parameter.default is inspect.Signature.empty,
            "schema": _wire_schema(
                parameter.annotation,
                default=parameter.default,
                parameter_name=parameter.name,
            ),
        }
        if parameter.default is not inspect.Signature.empty:
            item["default"] = _json_default(parameter.default)
        parameters.append(item)
    return parameters


def _capture_result_schema(name: str, method: object) -> dict:
    if name == "ping":
        return {"type": "boolean"}
    if name == "get_active_screenshot":
        return {"type": ["null", "string"]}
    annotation_schema = _wire_schema(inspect.signature(method).return_annotation)
    # All currently unannotated RPC methods except ping return structured mappings.
    return annotation_schema or {"type": "object"}


def _normalize_legacy_failure(value: dict[str, Any]) -> dict[str, Any]:
    details = value.get("details")
    data = dict(details) if isinstance(details, dict) else {}
    for key, item in value.items():
        if key not in {"code", "error", "error_code", "message", "ok", "success"}:
            data.setdefault(key, item)
    return {
        "code": value.get("code") or value.get("error_code") or "LEGACY_FAILURE",
        "message": str(value.get("message") or value.get("error") or "RPC failed"),
        "data": data,
    }


def capture_parameter_contract(cls: type) -> dict[str, list[dict[str, Any]]]:
    methods: dict[str, Any] = {}
    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        method = getattr(cls, name)
        if not callable(method):
            continue
        methods[name] = _capture_parameters(method)
    return methods


def _exposed_names(instance: object) -> frozenset[str]:
    return frozenset(
        name
        for name in dir(instance)
        if not name.startswith("_") and callable(getattr(instance, name))
    )


@pytest.fixture(scope="module")
def freecad_rpc_class():
    bootstrap_unit_test_runtime()
    from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

    return FreeCADRPC


def test_freecad_rpc_semantic_surface_matches_contract_snapshot(freecad_rpc_class):
    expected = _load_snapshot()["methods"]
    actual = capture_parameter_contract(freecad_rpc_class)
    assert actual == {name: contract["parameters"] for name, contract in expected.items()}


def test_freecad_rpc_result_schemas_are_valid_and_transport_neutral():
    snapshot = _load_snapshot()
    assert snapshot["schema_version"] == 3
    assert snapshot["listener_contract"] == {
        "phase1_validated": ["xmlrpc"],
        "phase4_required": ["xmlrpc", "jsonrpc2"],
        "post_phase5_deprecation": {
            "body": {
                "error": "xmlrpc_retired",
                "message": "XML-RPC is retired; use JSON-RPC 2.0 at /jsonrpc",
            },
            "headers": {
                "Cache-Control": "no-store",
                "Deprecation": "true",
                "Link": '</jsonrpc>; rel="successor-version"',
                "X-FreeCAD-MCP-Protocol": "jsonrpc-2.0",
            },
            "paths": ["/", "/RPC2"],
            "status": 410,
        },
        "post_phase5_negotiation": {
            "header": "X-FreeCAD-MCP-Protocol",
            "mismatch": {
                "response": {
                    "error": {
                        "code": -32005,
                        "data": {"expected": "jsonrpc-2.0"},
                        "message": "Protocol mismatch",
                    },
                    "id": None,
                    "jsonrpc": "2.0",
                },
                "status": 409,
            },
            "value": "jsonrpc-2.0",
        },
        "post_phase5_required": ["jsonrpc2"],
    }
    for method_name, contract in snapshot["methods"].items():
        for schema_name in ("result_schema", "normalized_error_schema"):
            schema = contract[schema_name]
            Draft202012Validator.check_schema(schema)
            types = schema.get("type", [])
            types = {types} if isinstance(types, str) else set(types)
            assert types <= _JSON_TYPES, (method_name, schema_name)
        assert all(parameter["schema"] for parameter in contract["parameters"])
        result_schema = contract["result_schema"]
        if result_schema.get("type") == "object":
            assert result_schema.get("properties"), method_name
            assert result_schema.get("oneOf") or result_schema.get("anyOf") or (
                result_schema.get("required")
            ), method_name
            assert all(result_schema["properties"].values()), method_name
        assert contract["normalized_error_schema"]["required"] == [
            "code",
            "data",
            "message",
        ]
        assert "signature" not in contract
        assert "docstring" not in contract

    normalization = snapshot["legacy_error_normalization"]
    assert normalization["failure_indicators"] == {"ok": False, "success": False}
    assert normalization["error_code_fields"] == ["code", "error_code"]
    assert normalization["error_message_fields"] == ["error", "message"]


def test_frozen_semantic_examples_are_json_native(freecad_rpc_class):
    snapshot = _load_snapshot()
    assert freecad_rpc_class
    for method_name, contract in snapshot["methods"].items():
        result_validator = Draft202012Validator(contract["result_schema"])
        error_validator = Draft202012Validator(contract["normalized_error_schema"])
        for example in contract["result_examples"]:
            result_validator.validate(example)
            decoded = json.loads(json.dumps(example, allow_nan=False))
            result_validator.validate(decoded)
            if isinstance(decoded, dict) and (
                decoded.get("success") is False or decoded.get("ok") is False
            ):
                error_validator.validate(_normalize_legacy_failure(decoded))
        for example in contract["normalized_error_examples"]:
            error_validator.validate(example)
        assert contract["result_examples"], method_name
        assert contract["normalized_error_examples"], method_name


def test_phase4_json_listener_round_trips_every_semantic_outcome():
    from addon.FreeCADMCP._shared.protocol.json_rpc import (
        encode_json_rpc_responses,
        json_rpc_error,
        json_rpc_success,
    )
    from addon.FreeCADMCP.rpc_server.json_rpc_errors import (
        json_rpc_error_from_result,
    )

    snapshot = _load_snapshot()
    converted_failures = 0
    for method_name, contract in snapshot["methods"].items():
        result_validator = Draft202012Validator(contract["result_schema"])
        error_validator = Draft202012Validator(contract["normalized_error_schema"])
        for index, example in enumerate(contract["result_examples"]):
            mapped = json_rpc_error_from_result(example)
            if mapped is None:
                response = json_rpc_success(index, example)
                decoded = json.loads(
                    encode_json_rpc_responses([response], batch=False)
                )
                result_validator.validate(decoded["result"])
                assert decoded["result"] == example
                continue
            converted_failures += 1
            error_validator.validate(mapped)
            response = json_rpc_error(
                index,
                mapped["code"],
                mapped["message"],
                mapped["data"],
            )
            decoded = json.loads(encode_json_rpc_responses([response], batch=False))
            error_validator.validate(decoded["error"])
            assert decoded["error"] == mapped
        assert contract["result_examples"], method_name

    assert converted_failures == 75


def test_phase5_json_client_converts_every_documented_failure_to_native_error():
    from addon.FreeCADMCP._shared.protocol.json_rpc import (
        encode_json_rpc_responses,
        json_rpc_error,
        json_rpc_success,
    )
    from addon.FreeCADMCP._shared.protocol.json_rpc_client import (
        JsonRpcRemoteError,
        decode_json_rpc_response,
    )
    from addon.FreeCADMCP.rpc_server.json_rpc_errors import (
        json_rpc_error_from_result,
    )

    snapshot = _load_snapshot()
    converted_failures = 0
    for method_name, contract in snapshot["methods"].items():
        for index, example in enumerate(contract["result_examples"]):
            mapped = json_rpc_error_from_result(example)
            if mapped is None:
                response = json_rpc_success(index, example)
                payload = encode_json_rpc_responses([response], batch=False)
                assert decode_json_rpc_response(payload, expected_id=index) == example
                continue

            converted_failures += 1
            response = json_rpc_error(
                index,
                mapped["code"],
                mapped["message"],
                mapped["data"],
            )
            payload = encode_json_rpc_responses([response], batch=False)
            with pytest.raises(JsonRpcRemoteError) as caught:
                decode_json_rpc_response(payload, expected_id=index)
            error = caught.value
            assert error.code == mapped["code"], method_name
            assert error.message == mapped["message"], method_name
            assert error.data == mapped["data"], method_name
            assert error.semantic_code == mapped["data"]["error_code"], method_name

    assert converted_failures == 75


def test_freecad_rpc_instance_exposes_same_public_names(freecad_rpc_class):
    expected_names = frozenset(_load_snapshot()["methods"])
    assert _exposed_names(freecad_rpc_class()) == expected_names
