"""Production listener-dispatch specimens for the semantic RPC contract."""

from __future__ import annotations

import inspect
import json
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
    document_lock = SimpleNamespace(
        is_enabled=lambda: True,
        get_request_identity=lambda: {
            "instance_id": "mcp-contract",
            "authenticated_session_id": "session-contract",
        },
    )
    rpc_module = inspect.getmodule(freecad_rpc_class)
    assert rpc_module is not None
    monkeypatch.setattr(rpc_module, "_import_document_lock", lambda: document_lock)
    monkeypatch.setattr(rpc_module, "document_lease_service", object())
    instance = freecad_rpc_class()
    dispatcher = SimpleXMLRPCDispatcher(allow_none=True, encoding=None)
    dispatcher.register_instance(instance)

    instance._acquire_document_lock_v2 = (
        lambda _selector, **_kwargs: expected["acquire_document_lock"]
    )
    actual = {
        "acquire_document_lock": dispatcher._dispatch(
            "acquire_document_lock", ("ContractDocument",)
        )
    }

    create_module = inspect.getmodule(freecad_rpc_class.create_document)
    assert create_module is not None
    monkeypatch.setattr(
        create_module,
        "_rpc_mod",
        lambda: SimpleNamespace(
            _import_document_lock=lambda: SimpleNamespace(
                get_request_identity=lambda: {}
            ),
            document_lease_service=None,
        ),
    )
    monkeypatch.setattr(create_module.FreeCAD, "getDocument", lambda _name: None)
    instance._request_checkpoint = lambda *_args, **_kwargs: None
    instance._current_inflight = lambda: None
    instance._dispatch_gui = lambda *_args, **_kwargs: True
    instance._unknown_mutation_evidence = lambda *_args, **_kwargs: {
        "document_health": {},
        "mutation_scope": {"declared_documents": ["Phase1ContractDocument"]},
    }
    actual["create_document"] = dispatcher._dispatch(
        "create_document", ("Phase1ContractDocument",)
    )
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
    runtime = SimpleNamespace(
        _freecad_version_parts=lambda: ("1", "2", "3"),
        rpc_server_actual_endpoint={"host": "127.0.0.1", "port": 9988},
        rpc_server_runtime_id="addon-runtime-contract",
        rpc_runtime_manifest=None,
        addon_loaded_at="loaded-contract",
        rpc_server_started_at="rpc-started-contract",
        rpc_session_manager=object(),
    )
    monkeypatch.setattr(status_module, "_rpc_mod", lambda: runtime)
    monkeypatch.setattr(
        status_module,
        "load_settings",
        lambda: {
            "profile_instance_id": "profile-contract",
            "rpc_bind_host": "127.0.0.1",
            "rpc_port": 9988,
            "document_lease_mode": "enforce",
        },
    )
    monkeypatch.setattr(status_module.FreeCAD, "getUserAppDataDir", lambda: "/profile/")
    monkeypatch.setattr(status_module.os, "getpid", lambda: 4242)
    monkeypatch.setattr(status_module, "_process_started_at", lambda: "process-contract")
    monkeypatch.setattr(status_module, "_boot_identity", lambda: "boot-contract")
    monkeypatch.setattr(
        status_module, "_profile_fingerprint", lambda: "profile-fingerprint-contract"
    )
    actual["get_instance_info"] = dispatcher._dispatch("get_instance_info", ())

    assert actual == expected
    snapshot = _snapshot()
    for method_name, value in actual.items():
        Draft202012Validator(snapshot["methods"][method_name]["result_schema"]).validate(
            value
        )
