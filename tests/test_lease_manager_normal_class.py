#!/usr/bin/env python3
"""Phase 6 contracts for the normally-defined lease client manager."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any

import pytest

import freecad_mcp.lease_manager as public_lease_manager
from freecad_mcp.lease_manager import (
    LeaseClientManager as LegacyLeaseClientManager,
)
from freecad_mcp.lease_manager import (
    LeaseCompatibilityResult as PublicLeaseCompatibilityResult,
)
from freecad_mcp.lease_manager import NativeSessionHandle as PublicNativeSessionHandle
from freecad_mcp.lease_manager_ops.lease_client_manager import LeaseClientManager
from freecad_mcp.lease_manager_ops.lease_compatibility_result import (
    LeaseCompatibilityResult,
)
from freecad_mcp.lease_manager_ops.lease_credential import LeaseCredential
from freecad_mcp.lease_manager_ops.native_session_handle import NativeSessionHandle
from tests.helpers.architecture_baseline import authority_symbol_census, load_manifest

pytestmark = pytest.mark.unit


_MANAGER_METHODS = {
    "__init__",
    "__repr__",
    "connected",
    "mark_connected",
    "close",
    "mark_disconnected",
    "store",
    "get",
    "require",
    "aliases_for",
    "add_alias",
    "migrate_alias",
    "revoke",
    "apply_heartbeat_response",
    "credentials_snapshot",
    "build_request_context",
    "build_heartbeat_payload",
    "build_heartbeat_request",
    "build_heartbeat_envelope",
    "redacted_status",
    "_require_connected_locked",
    "_require_open_locked",
    "_build_heartbeat_payload_locked",
    "redact_text",
    "redact_value",
    "_secret_snapshot_locked",
    "_redact_text_with_secrets",
    "_redact_text_locked",
}

_LEGACY_AUTHORITY_IMPORT_MARKERS = (
    "core_authority",
    "document_lease",
    "document_lock",
    "git_sidecar",
)
_RPC_CONTRACT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "freecad_rpc_contract_snapshot.json"
)
_PUBLIC_MANAGER_CALLABLES = {
    name
    for name in _MANAGER_METHODS
    if not name.startswith("_") and name != "connected"
}
_POSITIONAL = inspect.Parameter.POSITIONAL_OR_KEYWORD
_KEYWORD_ONLY = inspect.Parameter.KEYWORD_ONLY
_EMPTY = inspect.Parameter.empty
_LEGACY_OPERATION_PARAMETERS = {
    "mark_connected": (
        ("manager", _POSITIONAL, _EMPTY),
        ("session_token", _POSITIONAL, _EMPTY),
    ),
    "close": (
        ("manager", _POSITIONAL, _EMPTY),
        ("reason", _POSITIONAL, "MCP process shutdown"),
    ),
    "mark_disconnected": (
        ("manager", _POSITIONAL, _EMPTY),
        ("reason", _POSITIONAL, "connection closed"),
    ),
    "store": (
        ("manager", _POSITIONAL, _EMPTY),
        ("credential", _POSITIONAL, _EMPTY),
        ("canonical_paths", _KEYWORD_ONLY, ()),
        ("replace", _KEYWORD_ONLY, False),
    ),
    "get": (
        ("manager", _POSITIONAL, _EMPTY),
        ("document_session_uuid", _KEYWORD_ONLY, None),
        ("canonical_path", _KEYWORD_ONLY, None),
    ),
    "require": (
        ("manager", _POSITIONAL, _EMPTY),
        ("document_session_uuid", _KEYWORD_ONLY, None),
        ("canonical_path", _KEYWORD_ONLY, None),
    ),
    "aliases_for": (
        ("manager", _POSITIONAL, _EMPTY),
        ("document_session_uuid", _POSITIONAL, _EMPTY),
    ),
    "add_alias": (
        ("manager", _POSITIONAL, _EMPTY),
        ("document_session_uuid", _POSITIONAL, _EMPTY),
        ("canonical_path", _POSITIONAL, _EMPTY),
    ),
    "migrate_alias": (
        ("manager", _POSITIONAL, _EMPTY),
        ("old_path", _POSITIONAL, _EMPTY),
        ("new_path", _POSITIONAL, _EMPTY),
        ("document_session_uuid", _KEYWORD_ONLY, None),
        ("retain_old", _KEYWORD_ONLY, False),
    ),
    "revoke": (
        ("manager", _POSITIONAL, _EMPTY),
        ("document_session_uuid", _POSITIONAL, _EMPTY),
        ("reason", _KEYWORD_ONLY, _EMPTY),
        ("user_intervened", _KEYWORD_ONLY, False),
    ),
    "apply_heartbeat_response": (
        ("manager", _POSITIONAL, _EMPTY),
        ("response", _POSITIONAL, _EMPTY),
    ),
    "credentials_snapshot": (("manager", _POSITIONAL, _EMPTY),),
    "build_request_context": (
        ("manager", _POSITIONAL, _EMPTY),
        ("document_session_uuids", _KEYWORD_ONLY, ()),
        ("canonical_paths", _KEYWORD_ONLY, ()),
        ("operation_name", _KEYWORD_ONLY, ""),
        ("task_id", _KEYWORD_ONLY, ""),
        ("request_id", _KEYWORD_ONLY, None),
    ),
    "build_heartbeat_payload": (
        ("manager", _POSITIONAL, _EMPTY),
        ("current_operations", _POSITIONAL, None),
    ),
    "build_heartbeat_request": (
        ("manager", _POSITIONAL, _EMPTY),
        ("current_operations", _POSITIONAL, None),
        ("request_id", _KEYWORD_ONLY, None),
    ),
    "build_heartbeat_envelope": (
        ("manager", _POSITIONAL, _EMPTY),
        ("current_operations", _POSITIONAL, None),
        ("request_id", _KEYWORD_ONLY, None),
    ),
    "redacted_status": (("manager", _POSITIONAL, _EMPTY),),
    "_require_connected_locked": (("manager", _POSITIONAL, _EMPTY),),
    "_require_open_locked": (("manager", _POSITIONAL, _EMPTY),),
    "_build_heartbeat_payload_locked": (
        ("manager", _POSITIONAL, _EMPTY),
        ("current_operations", _POSITIONAL, _EMPTY),
    ),
    "redact_text": (
        ("manager", _POSITIONAL, _EMPTY),
        ("value", _POSITIONAL, _EMPTY),
        ("additional_secrets", _KEYWORD_ONLY, ()),
    ),
    "redact_value": (
        ("manager", _POSITIONAL, _EMPTY),
        ("value", _POSITIONAL, _EMPTY),
        ("additional_secrets", _KEYWORD_ONLY, ()),
    ),
    "_secret_snapshot_locked": (("manager", _POSITIONAL, _EMPTY),),
    "_redact_text_with_secrets": (
        ("value", _POSITIONAL, _EMPTY),
        ("secrets", _POSITIONAL, _EMPTY),
    ),
    "_redact_text_locked": (
        ("manager", _POSITIONAL, _EMPTY),
        ("value", _POSITIONAL, _EMPTY),
    ),
}


def _parameter_contract(value: object) -> tuple[tuple[str, object, object], ...]:
    return tuple(
        (parameter.name, parameter.kind, parameter.default)
        for parameter in inspect.signature(value).parameters.values()
    )


def _assert_import_only_shim(module: object, expected_all: tuple[str, ...]) -> None:
    tree = _source_tree(module)
    assert module.__all__ == expected_all
    for index, node in enumerate(tree.body):
        if (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        assert isinstance(node, ast.Assign), ast.dump(node)
        assert len(node.targets) == 1
        assert isinstance(node.targets[0], ast.Name)
        assert node.targets[0].id == "__all__"
        assert isinstance(node.value, ast.Tuple)
        assert all(
            isinstance(item, ast.Constant) and isinstance(item.value, str)
            for item in node.value.elts
        )
    assert not any(isinstance(node, ast.Call) for node in tree.body)


def _source_tree(module: object) -> ast.Module:
    return ast.parse(inspect.getsource(module))


def _import_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _credential(session: str, token: str) -> LeaseCredential:
    return LeaseCredential(
        lease_id=f"lease-{session}",
        document_session_uuid=session,
        generation=3,
        token=token,
    )


def test_manager_is_defined_normally_with_its_complete_current_surface():
    import freecad_mcp.lease_manager_ops.lease_client_manager as defining_module

    tree = _source_tree(defining_module)
    class_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LeaseClientManager"
    ]
    assert len(class_nodes) == 1
    class_node = class_nodes[0]
    methods = {
        node.name
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert methods == _MANAGER_METHODS
    assert {
        name
        for name, member in inspect.getmembers(LeaseClientManager, callable)
        if not name.startswith("_")
    } == _PUBLIC_MANAGER_CALLABLES
    assert LegacyLeaseClientManager is LeaseClientManager
    assert PublicNativeSessionHandle is NativeSessionHandle
    assert PublicLeaseCompatibilityResult is LeaseCompatibilityResult
    assert public_lease_manager.__all__.count("NativeSessionHandle") == 1
    assert public_lease_manager.__all__.count("LeaseCompatibilityResult") == 1
    assert defining_module.__all__ == (
        "LeaseClientManager",
        "bind_lease_client_manager",
    )
    assert _parameter_contract(LeaseClientManager) == (
        ("args", inspect.Parameter.VAR_POSITIONAL, _EMPTY),
        ("kwargs", inspect.Parameter.VAR_KEYWORD, _EMPTY),
    )
    assert not any(
        isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "LeaseClientManager"
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
        for node in tree.body
    )
    imports = _import_names(tree)
    assert "lease_client_manager_bindings" not in inspect.getsource(defining_module)
    assert not {
        dependency
        for dependency in imports
        if dependency.rsplit(".", 1)[-1]
        in {
            "lease_client_credential_ops",
            "lease_client_heartbeat_ops",
            "lease_client_status_ops",
        }
    }
    forbidden_dynamic_calls = {"__import__", "import_module", "setattr"}
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if isinstance(call.func, ast.Name):
            assert call.func.id not in forbidden_dynamic_calls
        elif isinstance(call.func, ast.Attribute):
            assert call.func.attr not in forbidden_dynamic_calls
    for method in class_node.body:
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not (
                len(method.body) == 1
                and isinstance(method.body[0], ast.Return)
                and isinstance(method.body[0].value, ast.Call)
                and method.name
                not in {
                    "_redact_text_locked",
                }
            )


@pytest.mark.parametrize(
    ("module_name", "member_names"),
    (
        (
            "lease_client_credential_ops",
            (
                "mark_connected",
                "close",
                "mark_disconnected",
                "store",
                "get",
                "require",
                "aliases_for",
                "add_alias",
                "migrate_alias",
                "revoke",
            ),
        ),
        (
            "lease_client_heartbeat_ops",
            (
                "apply_heartbeat_response",
                "credentials_snapshot",
                "build_request_context",
                "build_heartbeat_payload",
                "build_heartbeat_request",
                "build_heartbeat_envelope",
            ),
        ),
        (
            "lease_client_status_ops",
            (
                "redacted_status",
                "_require_connected_locked",
                "_require_open_locked",
                "_build_heartbeat_payload_locked",
                "redact_text",
                "redact_value",
                "_secret_snapshot_locked",
                "_redact_text_with_secrets",
                "_redact_text_locked",
            ),
        ),
    ),
)
def test_retired_operation_modules_are_declarative_compatibility_shims(
    module_name: str, member_names: tuple[str, ...]
):
    module = __import__(f"freecad_mcp.lease_manager_ops.{module_name}", fromlist=["*"])
    _assert_import_only_shim(module, member_names)
    for name in member_names:
        value = getattr(module, name)
        assert _parameter_contract(value) == _LEGACY_OPERATION_PARAMETERS[name]


def test_old_operation_paths_still_accept_manager_as_a_keyword(tmp_path: Path):
    import freecad_mcp.lease_manager_ops.lease_client_credential_ops as credential_ops
    import freecad_mcp.lease_manager_ops.lease_client_status_ops as status_ops

    manager = LeaseClientManager()
    credential_ops.mark_connected(manager=manager, session_token="keyword-session")
    credential = _credential("keyword-document", "keyword-credential")
    credential_ops.store(
        manager=manager,
        credential=credential,
        canonical_paths=(tmp_path / "keyword.FCStd",),
    )
    assert (
        credential_ops.get(
            manager=manager,
            document_session_uuid="keyword-document",
        )
        is credential
    )
    assert status_ops.redacted_status(manager=manager)["connected"] is True


def test_legacy_binding_and_init_shims_remain_callable_without_class_mutation():
    import freecad_mcp.lease_manager_ops.lease_client_manager as defining_module
    import freecad_mcp.lease_manager_ops.lease_client_manager_bindings as bindings
    import freecad_mcp.lease_manager_ops.lease_client_manager_init as init_shim

    _assert_import_only_shim(bindings, ("bind_lease_client_manager",))
    _assert_import_only_shim(init_shim, ("init_manager",))
    assert (
        bindings.bind_lease_client_manager is defining_module.bind_lease_client_manager
    )
    assert init_shim.init_manager is defining_module._compat_init_manager
    assert _parameter_contract(bindings.bind_lease_client_manager) == (
        ("LeaseClientManager", _POSITIONAL, _EMPTY),
    )
    assert _parameter_contract(init_shim.init_manager) == (
        ("manager", _POSITIONAL, _EMPTY),
        ("session_token", _KEYWORD_ONLY, None),
    )

    class UnrelatedClass:
        pass

    unrelated_before = dict(UnrelatedClass.__dict__)
    manager_before = dict(LeaseClientManager.__dict__)
    assert bindings.bind_lease_client_manager(LeaseClientManager=UnrelatedClass) is None
    assert dict(UnrelatedClass.__dict__) == unrelated_before
    assert dict(LeaseClientManager.__dict__) == manager_before

    importlib.reload(bindings)
    importlib.reload(init_shim)
    assert dict(LeaseClientManager.__dict__) == manager_before

    class InitializerTrap(LeaseClientManager):
        def __init__(self, **kwargs):
            raise AssertionError(f"dynamic initializer dispatch: {kwargs!r}")

    initialized = object.__new__(InitializerTrap)
    init_shim.init_manager(manager=initialized, session_token="fresh-session")
    assert initialized.connected is True
    assert initialized.redacted_status()["credentials"] == []


def test_construction_alias_reconnect_and_redaction_behavior_remains_intact(
    tmp_path: Path,
):
    session_secret = "native-session-secret"
    credential_secret = "lease-credential-secret"
    manager = LeaseClientManager(session_token=session_secret)
    credential = _credential("document-a", credential_secret)
    source = tmp_path / "source.FCStd"
    destination = tmp_path / "destination.FCStd"

    assert manager.connected is True
    assert session_secret not in repr(manager)
    assert manager.store(credential, canonical_paths=(source,)) is credential
    assert credential_secret not in repr(manager)
    assert manager.get(document_session_uuid="document-a") is credential
    assert manager.get(canonical_path=source) is credential
    assert manager.migrate_alias(source, destination) is credential
    assert manager.get(canonical_path=source) is None
    assert manager.get(canonical_path=destination) is credential

    manager.mark_disconnected(f"lost {session_secret} {credential_secret}")
    assert manager.connected is False
    assert manager.get(document_session_uuid="document-a") is credential
    assert session_secret not in manager.redacted_status()["disconnect_reason"]
    assert credential_secret not in manager.redacted_status()["disconnect_reason"]

    replacement_secret = "replacement-session-secret"
    manager.mark_connected(replacement_secret)
    assert manager.connected is True
    assert manager.get(canonical_path=destination) is credential
    unsafe = {
        "message": f"{session_secret}/{credential_secret}/{replacement_secret}",
        "nested": [credential_secret, {credential_secret: replacement_secret}],
    }
    redacted = manager.redact_value(
        unsafe,
        additional_secrets=(session_secret,),
    )
    assert redacted == {
        "message": "[REDACTED]/[REDACTED]/[REDACTED]",
        "nested": ["[REDACTED]", {"[REDACTED]": "[REDACTED]"}],
    }
    assert unsafe["nested"][0] == credential_secret
    assert all(
        secret not in repr(redacted)
        for secret in (session_secret, credential_secret, replacement_secret)
    )


@pytest.mark.parametrize("invalid", (None, 0, b"native-session"))
def test_native_session_handle_requires_a_string(invalid: object):
    with pytest.raises(TypeError):
        NativeSessionHandle(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid", ("", "  \t"))
def test_native_session_handle_requires_a_nonempty_value(invalid: str):
    with pytest.raises(ValueError):
        NativeSessionHandle(invalid)


def test_native_session_handle_is_opaque_immutable_and_value_like():
    opaque_id = "native-session-id-that-must-not-be-rendered"
    handle = NativeSessionHandle(opaque_id)

    assert handle.opaque_id == opaque_id
    assert handle.to_native_argument() == opaque_id
    assert handle == NativeSessionHandle(opaque_id)
    assert handle != NativeSessionHandle("other-native-session")
    assert hash(handle) == hash(NativeSessionHandle(opaque_id))
    assert opaque_id not in repr(handle)
    assert opaque_id not in str(handle)
    assert [item.name for item in fields(NativeSessionHandle)] == ["opaque_id"]
    assert NativeSessionHandle.__slots__ == ("opaque_id",)
    assert not hasattr(handle, "__dict__")
    assert _parameter_contract(NativeSessionHandle) == (
        ("opaque_id", _POSITIONAL, _EMPTY),
    )
    assert _parameter_contract(handle.to_native_argument) == ()
    with pytest.raises((AttributeError, FrozenInstanceError)):
        handle.opaque_id = "replacement"  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        handle.authority = "write"  # type: ignore[attr-defined]

    public_data = {
        name
        for name in dir(handle)
        if not name.startswith("_") and not callable(getattr(handle, name))
    }
    assert public_data == {"opaque_id"}
    public_methods = {
        name
        for name, member in inspect.getmembers(NativeSessionHandle, callable)
        if not name.startswith("_")
    }
    assert public_methods == {"to_native_argument"}


def test_compatibility_result_is_copied_immutable_and_diagnostic_only():
    source: dict[str, Any] = {
        "owner": "historic-owner",
        "generation": 7,
        "heartbeat": {"status": "STALE", "details": ["historic"]},
    }
    result = LeaseCompatibilityResult(source)

    first = result.to_dict()
    source["heartbeat"]["details"].append("caller-mutated")
    assert first == {
        "owner": "historic-owner",
        "generation": 7,
        "heartbeat": {"status": "STALE", "details": ["historic"]},
    }
    first["heartbeat"]["details"].append("returned-mutated")
    assert result.to_dict()["heartbeat"]["details"] == ["historic"]
    second = result.to_dict()
    second["heartbeat"]["details"].clear()
    assert result.to_dict()["heartbeat"]["details"] == ["historic"]
    assert all(
        value not in repr(result) for value in ("historic-owner", "STALE", "historic")
    )
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        result.payload = {}  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        result._payload_json = "{}"  # type: ignore[misc]
    assert not hasattr(result, "__dict__")

    public_methods = {
        name
        for name, member in inspect.getmembers(LeaseCompatibilityResult, callable)
        if not name.startswith("_")
    }
    assert public_methods == {"to_dict"}


def test_compatibility_result_redacts_nested_inline_secrets_and_keys():
    secrets = (
        "AUTH-SECRET",
        "TOKEN-SECRET",
        "CREDENTIAL-SECRET",
        "CAPABILITY-SECRET",
        "GRANT-SECRET",
    )
    result = LeaseCompatibilityResult(
        {
            "message": "Authorization: Bearer AUTH-SECRET token=TOKEN-SECRET",
            "nested": [
                "credentials=CREDENTIAL-SECRET capability=CAPABILITY-SECRET",
                {"note grant=GRANT-SECRET": "Authorization: Basic AUTH-SECRET"},
                '{"token":"TOKEN-SECRET"}',
                '{"session_token": "TOKEN-SECRET"}',
                '{"capability":{"status":"active","value":"native-write"}}',
                'credentials={"primary":"CREDENTIAL-SECRET"}',
                "credentialPayload=CREDENTIAL-SECRET",
                "authorizationHeader=AUTH-SECRET",
                "secretValue=TOKEN-SECRET",
                "capabilityContext=CAPABILITY-SECRET",
                "grantMaterial=GRANT-SECRET",
                "rpcAuthHeader=AUTH-SECRET",
                "authorization header=AUTH-SECRET",
                "auth.header=AUTH-SECRET",
                "credential payload=CREDENTIAL-SECRET",
                "capability/context=CAPABILITY-SECRET",
            ],
        }
    )
    payload = result.to_dict()

    assert payload == {
        "message": "[REDACTED]",
        "nested": [
            "[REDACTED]",
            {"[REDACTED]": "[REDACTED]"},
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
            "[REDACTED]",
        ],
    }
    assert all(secret not in json.dumps(payload) for secret in secrets)
    assert all(secret not in repr(result) for secret in secrets)


def test_compatibility_result_accepts_frozen_public_diagnostics():
    contract = json.loads(_RPC_CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    instance_info = contract["production_listener_examples"]["get_instance_info"]
    instance_info["capability_status"] = "available"
    instance_info["signature_status"] = "verified"

    assert LeaseCompatibilityResult(instance_info).to_dict() == instance_info


@pytest.mark.parametrize(
    "payload",
    (
        {"token": "raw-token"},
        {"session_token": "raw-session"},
        {"lease_credentials": [{"token": "raw-token"}]},
        {"diagnostic": {"credentials": {"password": "raw-password"}}},
        {"history": [{"capability": "native-write"}]},
        {"nested": {"grant": {"authorization": "bearer-value"}}},
    ),
)
def test_compatibility_result_rejects_credential_and_capability_material_recursively(
    payload: Mapping[str, Any],
):
    secret_text = " ".join(str(value) for value in payload.values())
    with pytest.raises((TypeError, ValueError)) as raised:
        LeaseCompatibilityResult(payload)
    assert secret_text not in str(raised.value)


@pytest.mark.parametrize(
    "field",
    (
        "auth_header",
        "credential_payload",
        "capability_context",
        "grant_material",
        "refresh_token",
        "authorizationHeader",
        "leaseCredentials",
        "rpcAuth",
        "RPCAuth",
        "RPCAuthorizationHeader",
        "sessionToken",
        "sessiontoken",
        "leasecredentials",
        "authtoken",
        "capabilitygrant",
        "token_status",
        "secret_available",
        "authority",
        "authorities",
        "authorized",
        "authorisation",
        "permissions",
        "privilege",
        "authorization header",
        "auth.header",
        "credential payload",
        "capability/context",
    ),
)
def test_compatibility_result_rejects_compound_authority_fields(field: str):
    with pytest.raises(ValueError) as raised:
        LeaseCompatibilityResult({field: "TOPSECRET"})
    assert str(raised.value) == (
        "compatibility result contains non-public authority data"
    )
    assert "TOPSECRET" not in str(raised.value)


def test_new_phase_six_types_do_not_depend_on_legacy_authority_modules():
    import freecad_mcp.lease_manager_ops.lease_client_manager as manager_module
    import freecad_mcp.lease_manager_ops.lease_compatibility_result as result_module
    import freecad_mcp.lease_manager_ops.native_session_handle as handle_module

    for module in (manager_module, result_module, handle_module):
        tree = _source_tree(module)
        imports = _import_names(tree)
        assert not {
            dependency
            for dependency in imports
            if any(marker in dependency for marker in _LEGACY_AUTHORITY_IMPORT_MARKERS)
        }, (module.__name__, imports)
        assert not any(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "__import__")
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                )
            )
            for node in ast.walk(tree)
        )

    assert authority_symbol_census() == load_manifest()["authority_symbol_census"]
