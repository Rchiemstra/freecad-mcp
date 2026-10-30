"""Merge add-on service RPCs into the authoritative semantic contract snapshot.

Run with ``python -m scripts.update_addon_rpc_contract``. Like the Part 3 updater,
capture public parameters with the contract helper and preserve unrelated entries.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/freecad_rpc_contract_snapshot.json"
)
METHODS = ("list_addons", "describe_addon", "invoke_addon_operation")


def main() -> None:
    bootstrap_unit_test_runtime()
    from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC
    from tests.freecad.test_freecad_rpc_contract_snapshot import (
        _normalize_legacy_failure,
        capture_parameter_contract,
    )
    from tests.helpers.addon_services import NativeDocument, host, registry_with

    # Exercise the real handlers and registry with the same native boundary double
    # used by the bridge unit tests; no FreeCAD installation or provider is loaded.
    registry = registry_with(lambda context, arguments: {"value": arguments["value"]})
    service, _, _ = host(NativeDocument(), registry)
    unavailable, _, _ = host(NativeDocument(), None)
    calls = {
        "list_addons": (),
        "describe_addon": ("Example",),
        "invoke_addon_operation": ("Target", "Example", "run", {"value": 1}),
    }
    fields = {
        "success": {"type": "boolean"},
        "error": {"type": "string"},
        "error_code": {"type": "string"},
        "committed": {"type": ["boolean", "null"]},
        "outcome": {"enum": ["committed", "rejected", "uncertain"]},
        "retry_safe": {"type": "boolean"},
    }
    success_fields = {
        "list_addons": {"addons": {"type": "array", "items": {"type": "object"}}},
        "describe_addon": {"addon": {"type": "object"}},
        "invoke_addon_operation": {
            "document_name": {"type": "string"},
            "addon_id": {"type": "string"},
            "operation": {"type": "string"},
            "result": {
                "type": ["array", "boolean", "integer", "null", "number", "object", "string"]
            },
            "after_commit_results": {"type": "array"},
        },
    }
    error_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "code": {"type": ["integer", "string"]},
            "data": {"type": "object", "additionalProperties": True},
            "message": {"type": "string"},
        },
        "required": ["code", "data", "message"],
    }
    snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parameters = capture_parameter_contract(FreeCADRPC)
    for name in METHODS:
        success = getattr(service, name)(*calls[name])
        failure = getattr(unavailable, name)(*calls[name])
        assert success["success"] is True
        assert failure["error_code"] == "ADDON_SERVICES_UNAVAILABLE"
        required = list(success_fields[name])
        if name == "invoke_addon_operation":
            required.remove("after_commit_results")
            required.extend(("committed", "outcome", "retry_safe"))
        snapshot["methods"][name] = {
            "parameters": parameters[name],
            "result_schema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {**fields, **success_fields[name]},
                "oneOf": [
                    {
                        "properties": {"success": {"const": True}},
                        "required": ["success", *required],
                    },
                    {
                        "properties": {"success": {"const": False}},
                        "required": ["success", "error", "error_code"],
                    },
                ],
            },
            "result_examples": [success, failure],
            "normalized_error_schema": error_schema,
            "normalized_error_examples": [_normalize_legacy_failure(failure)],
        }
    FIXTURE.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
