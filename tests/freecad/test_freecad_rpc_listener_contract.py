"""Production listener-dispatch specimens for the semantic RPC contract."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from xmlrpc.server import SimpleXMLRPCDispatcher

import pytest
from jsonschema.validators import Draft202012Validator

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parent / "fixtures/freecad_rpc_contract_snapshot.json"


@pytest.fixture(scope="module")
def freecad_rpc_class():
    bootstrap_unit_test_runtime()
    from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC

    return FreeCADRPC


def _snapshot():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_production_methods_dispatch_the_frozen_listener_examples(
    freecad_rpc_class, monkeypatch
):
    expected = _snapshot()["production_listener_examples"]
    default_instance = freecad_rpc_class()
    freecad = SimpleNamespace(
        getDocument=lambda _name: None,
        listDocuments=dict,
        getUserAppDataDir=lambda: "/profile/",
    )
    collaboration_collaborators = replace(
        default_instance._collaboration_collaborators,
        freecad=freecad,
    )
    execution_collaborators = replace(
        default_instance._execution_collaborators,
        freecad=freecad,
        session_manager=object(),
        runtime_manifest=None,
        actual_endpoint={"host": "127.0.0.1", "port": 9988},
        runtime_id="addon-runtime-contract",
        server_started_at="rpc-started-contract",
        addon_loaded_at="loaded-contract",
        freecad_version_parts=lambda: ("1", "2", "3"),
        load_settings=lambda: {
            "profile_instance_id": "profile-contract",
            "rpc_bind_host": "127.0.0.1",
            "rpc_port": 9988,
            "document_lease_mode": "enforce",
        },
        process_started_at="process-contract",
        boot_id="boot-contract",
        profile_fingerprint="profile-fingerprint-contract",
    )
    instance = freecad_rpc_class(
        collaboration_collaborators=collaboration_collaborators,
        lifecycle_collaborators=default_instance._lifecycle_collaborators,
        execution_collaborators=execution_collaborators,
        cad_collaborators=replace(
            default_instance._cad_collaborators,
            compatibility_api=collaboration_collaborators.compatibility_api,
            freecad=freecad,
        ),
    )
    dispatcher = SimpleXMLRPCDispatcher(allow_none=True, encoding=None)
    dispatcher.register_instance(instance)

    actual = {
        "acquire_document_lock": dispatcher._dispatch(
            "acquire_document_lock", ("ContractDocument",)
        )
    }
    assert actual["acquire_document_lock"] == {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }

    create_module = inspect.getmodule(freecad_rpc_class.create_document)
    assert create_module is not None
    monkeypatch.setattr(create_module.FreeCAD, "getDocument", lambda _name: None)
    instance._request_checkpoint = lambda *_args, **_kwargs: None
    instance._current_inflight = lambda: None
    instance._create_document_gui = lambda _name: True
    instance._dispatch_gui = lambda callback: callback()
    instance._unknown_mutation_evidence = lambda *_args, **_kwargs: {
        "document_health": {},
        "mutation_scope": {"declared_documents": ["Phase1ContractDocument"]},
    }
    actual["create_document"] = dispatcher._dispatch(
        "create_document", ("Phase1ContractDocument",)
    )
    instance._dispatch_gui = lambda *_args, **_kwargs: True
    actual["create_object"] = dispatcher._dispatch(
        "create_object",
        ("ContractDocument", {"Name": "ContractObject", "Type": "Part::Feature"}),
    )
    instance._dispatch_gui = lambda *_args, **_kwargs: expected["get_object"]
    actual["get_object"] = dispatcher._dispatch(
        "get_object", ("ContractDocument", "ContractObject")
    )
    actual["ping"] = dispatcher._dispatch("ping", ())

    status_module = inspect.getmodule(freecad_rpc_class.get_instance_info)
    assert status_module is not None
    monkeypatch.setattr(status_module.os, "getpid", lambda: 4242)
    actual["get_instance_info"] = dispatcher._dispatch("get_instance_info", ())

    native_actual = {
        name: value
        for name, value in actual.items()
        if name != "acquire_document_lock"
    }
    native_expected = {
        name: value
        for name, value in expected.items()
        if name != "acquire_document_lock"
    }
    assert native_actual == native_expected
    snapshot = _snapshot()
    for method_name, value in actual.items():
        schema = snapshot["methods"][method_name]["result_schema"]
        Draft202012Validator(schema).validate(value)
