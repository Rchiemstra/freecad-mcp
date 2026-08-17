"""Merge Part 3 RPC methods into the authoritative contract snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime
from tests.test_freecad_rpc_contract_snapshot import capture_parameter_contract

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "freecad_rpc_contract_snapshot.json"

PART3_METHODS = (
    "get_semantic_revisions",
    "begin_checked_edit",
    "commit_checked_property",
    "cancel_checked_edit",
)


def _template_error_block() -> dict[str, Any]:
    return {
        "normalized_error_examples": [
            {
                "code": "DOCUMENT_CONFLICT",
                "data": {
                    "changed_semantic_keys": ["ObjectModel:Target"],
                    "current_revisions": {"ObjectModel:Target": 4},
                    "expected_revisions": {"ObjectModel:Target": 3},
                    "request_id": "part3-example",
                    "error_code": "DOCUMENT_CONFLICT",
                },
                "message": "document revision conflict",
            },
            {
                "code": "DOCUMENT_LIFECYCLE_REJECTED",
                "data": {
                    "current_lifecycle_epoch": 3,
                    "expected_lifecycle_epoch": 2,
                    "error_code": "DOCUMENT_LIFECYCLE_REJECTED",
                },
                "message": "document lifecycle changed",
            },
        ],
        "normalized_error_schema": {
            "additionalProperties": False,
            "properties": {
                "code": {"type": ["integer", "string"]},
                "data": {
                    "additionalProperties": True,
                    "properties": {
                        "changed_semantic_keys": {
                            "items": {"type": "string"},
                            "type": "array",
                        },
                        "current_lifecycle_epoch": {"type": "integer"},
                        "current_revisions": {
                            "additionalProperties": {"type": "integer"},
                            "type": "object",
                        },
                        "error_code": {"type": "string"},
                        "expected_lifecycle_epoch": {"type": "integer"},
                        "expected_revisions": {
                            "additionalProperties": {"type": "integer"},
                            "type": "object",
                        },
                        "request_id": {"type": ["null", "string"]},
                    },
                    "type": "object",
                },
                "message": {"type": "string"},
            },
            "required": ["code", "data", "message"],
            "type": "object",
        },
    }


def _result_examples(method: str) -> list[dict[str, Any]]:
    if method == "get_semantic_revisions":
        return [
            {
                "success": True,
                "document_uid": "uid-example",
                "document_instance_id": 1,
                "lifecycle_epoch": 1,
                "document_name": "Model",
                "revisions": [
                    {
                        "kind": "ObjectModel",
                        "subject": "Target",
                        "revision": 2,
                    }
                ],
            },
            {"success": False, "error": "example-error", "error_code": "DOCUMENT_NOT_FOUND"},
        ]
    if method == "begin_checked_edit":
        return [
            {
                "success": True,
                "session_id": "session-example",
                "document_uid": "uid-example",
                "document_instance_id": 1,
                "lifecycle_epoch": 1,
                "document_name": "Model",
                "revisions": [],
            },
            {"success": False, "error": "example-error", "error_code": "LEASE_PROTOCOL_REQUIRED"},
        ]
    if method == "commit_checked_property":
        return [
            {
                "success": True,
                "ok": True,
                "committed": True,
                "operation_id": "op-example",
                "status": "Committed",
                "published_revisions": [],
                "published_semantic_keys": [],
            },
            {
                "success": False,
                "error_code": "DOCUMENT_CONFLICT",
                "error": "document revision conflict",
                "changed_semantic_keys": ["ObjectModel:Target"],
                "expected_revisions": {"ObjectModel:Target": 2},
                "current_revisions": {"ObjectModel:Target": 3},
            },
        ]
    return [
        {"success": True, "cancelled": True, "session_id": "session-example"},
        {"success": False, "error_code": "DOCUMENT_LIFECYCLE_REJECTED", "error": "stale"},
    ]


def _result_schema(method: str) -> dict[str, Any]:
    return {
        "additionalProperties": True,
        "oneOf": [
            {
                "properties": {"success": {"const": True}},
                "required": ["success"],
            },
            {
                "properties": {"success": {"const": False}},
                "required": ["success"],
            },
        ],
        "properties": {
            "success": {"type": "boolean"},
            "ok": {"type": "boolean"},
            "error": {"type": "string"},
            "error_code": {"type": "string"},
            "committed": {"type": "boolean"},
            "cancelled": {"type": "boolean"},
            "session_id": {"type": "string"},
            "operation_id": {"type": "string"},
            "document_uid": {"type": "string"},
            "document_instance_id": {"type": "integer"},
            "lifecycle_epoch": {"type": "integer"},
            "document_name": {"type": ["null", "string"]},
            "revisions": {"type": "array"},
            "published_revisions": {"type": "array"},
            "published_semantic_keys": {"type": "array"},
            "changed_semantic_keys": {"type": "array"},
            "expected_revisions": {"type": "object"},
            "current_revisions": {"type": "object"},
        },
        "type": "object",
    }


def main() -> None:
    bootstrap_unit_test_runtime()
    from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC
    from tests.test_freecad_rpc_contract_snapshot import capture_parameter_contract

    snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
    methods = snapshot.setdefault("methods", {})
    template = _template_error_block()
    captured = capture_parameter_contract(FreeCADRPC)

    for method_name, parameters in captured.items():
        if method_name in methods:
            methods[method_name]["parameters"] = parameters

    for method_name in PART3_METHODS:
        method = getattr(FreeCADRPC, method_name)
        entry = dict(template)
        entry["parameters"] = captured[method_name]
        entry["result_schema"] = _result_schema(method_name)
        entry["result_examples"] = _result_examples(method_name)
        methods[method_name] = entry

    FIXTURE.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
