"""Contracts for the add-on's thin native collaboration bridge."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = ROOT / "addon" / "FreeCADMCP"
MODULE_PATH = ADDON_ROOT / "collaboration_api.py"

pytestmark = pytest.mark.unit


def _load_package_module():
    return importlib.import_module("addon.FreeCADMCP.collaboration_api")


class _NativeDocument:
    def __init__(self, result: object) -> None:
        self.result = result
        self.callbacks: list[object] = []
        self.structural_scopes: list[bool] = []

    def commitCompatibilityMutation(self, callback, *, structural=False):
        self.callbacks.append(callback)
        self.structural_scopes.append(structural)
        return self.result


def test_constructor_is_keyword_only_and_preserves_the_lookup_identity() -> None:
    api_type = _load_package_module().CollaborationAPI

    def lookup(name):
        return name

    api = api_type(document_lookup=lookup)

    assert api._document_lookup is lookup
    with pytest.raises(TypeError):
        api_type(lookup)


def test_bridge_resolves_once_and_returns_the_exact_native_result() -> None:
    api_type = _load_package_module().CollaborationAPI
    result = {"status": "Committed", "revisions": {"UnknownModel": 7}}
    document = _NativeDocument(result)
    document_name = "Model"

    def callback():
        return None

    lookup_calls: list[object] = []

    def lookup(name):
        lookup_calls.append(name)
        return document

    api = api_type(document_lookup=lookup)

    actual = api.commit_compatibility_mutation(document_name, callback)

    assert actual is result
    assert lookup_calls == [document_name]
    assert lookup_calls[0] is document_name
    assert document.callbacks == [callback]
    assert document.callbacks[0] is callback
    assert document.structural_scopes == [False]


def test_bridge_forwards_only_the_explicit_structural_scope() -> None:
    api_type = _load_package_module().CollaborationAPI
    document = _NativeDocument({"status": "Committed"})

    api_type(document_lookup=lambda _name: document).commit_compatibility_mutation(
        "Model", lambda: None, structural=True
    )

    assert document.structural_scopes == [True]


def test_bridge_propagates_lookup_and_native_failures_without_translation() -> None:
    api_type = _load_package_module().CollaborationAPI
    lookup_failure = RuntimeError("lookup failed")
    native_failure = ValueError("native callback failed")

    def failed_lookup(_name):
        raise lookup_failure

    with pytest.raises(RuntimeError) as lookup_info:
        api_type(document_lookup=failed_lookup).commit_compatibility_mutation(
            "Model",
            lambda: None,
        )
    assert lookup_info.value is lookup_failure

    class FailedNativeDocument:
        def commitCompatibilityMutation(self, _callback, *, structural=False):
            assert structural is False
            raise native_failure

    with pytest.raises(ValueError) as native_info:
        api_type(
            document_lookup=lambda _name: FailedNativeDocument()
        ).commit_compatibility_mutation("Model", lambda: None)
    assert native_info.value is native_failure


@pytest.mark.parametrize("document_lookup", [None, object(), "getDocument"])
def test_constructor_rejects_a_non_callable_lookup(document_lookup: object) -> None:
    api_type = _load_package_module().CollaborationAPI

    with pytest.raises(TypeError, match="document_lookup must be callable"):
        api_type(document_lookup=document_lookup)


def test_non_callable_callback_fails_before_document_resolution() -> None:
    api_type = _load_package_module().CollaborationAPI
    lookup_calls: list[object] = []

    def lookup(name):
        lookup_calls.append(name)
        return _NativeDocument(object())

    with pytest.raises(TypeError, match="callback must be callable"):
        api_type(document_lookup=lookup).commit_compatibility_mutation(
            "Model",
            object(),
        )

    assert lookup_calls == []


def test_missing_document_fails_closed() -> None:
    api_type = _load_package_module().CollaborationAPI

    with pytest.raises(LookupError, match="returned no document"):
        api_type(document_lookup=lambda _name: None).commit_compatibility_mutation(
            "Missing",
            lambda: None,
        )


def test_compose_lane_uses_adapter_fallback_without_native_commit() -> None:
    api_type = _load_package_module().CollaborationAPI
    for document in (object(), type("Document", (), {"commitCompatibilityMutation": 7})()):
        callback_ran = []
        result = api_type(
            document_lookup=lambda _name, document=document: document
        ).commit_compatibility_mutation("Model", lambda: callback_ran.append(None))
        assert result == {"status": "Committed", "committed": True}
        assert callback_ran == [None]


def test_native_lane_requires_commit_compatibility_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_type = _load_package_module().CollaborationAPI
    monkeypatch.setenv("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION", "1")

    for document in (object(), type("Document", (), {"commitCompatibilityMutation": 7})()):
        with pytest.raises(
            TypeError,
            match=r"document must provide commitCompatibilityMutation\(\)",
        ):
            api_type(
                document_lookup=lambda _name, document=document: document
            ).commit_compatibility_mutation("Model", lambda: None)


def test_public_signatures_expose_no_caller_supplied_authority_inputs() -> None:
    api_type = _load_package_module().CollaborationAPI

    assert list(inspect.signature(api_type).parameters) == ["document_lookup"]
    assert inspect.signature(api_type).parameters["document_lookup"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert list(
        inspect.signature(api_type.commit_compatibility_mutation).parameters
    ) == ["self", "document_name", "callback", "structural"]
    assert inspect.signature(api_type.commit_compatibility_mutation).parameters[
        "structural"
    ].kind is inspect.Parameter.KEYWORD_ONLY
    assert _load_package_module().__all__ == ["CollaborationAPI"]


def test_module_supports_the_flat_addon_import_convention(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ADDON_ROOT))
    sys.modules.pop("collaboration_api", None)

    flat_module = importlib.import_module("collaboration_api")
    result = object()
    document = _NativeDocument(result)

    def callback():
        return None

    actual = flat_module.CollaborationAPI(
        document_lookup=lambda _name: document
    ).commit_compatibility_mutation("Model", callback)

    assert actual is result
    assert document.callbacks == [callback]


def test_bridge_has_no_upward_or_legacy_authority_dependencies() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    forbidden_roots = {
        "capabilities",
        "dispatch",
        "document_lease",
        "document_lock",
        "rpc_server",
        "runtime",
        "transport",
    }
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_roots.add((node.module or "").partition(".")[0])

    assert not imported_roots & forbidden_roots
    assert not any(isinstance(node, (ast.Global, ast.Nonlocal)) for node in ast.walk(tree))


def test_bridge_surface_cannot_accept_identity_or_grant_inputs() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    forbidden = {
        "capability",
        "confirmation",
        "credential",
        "generation",
        "identity",
        "owner",
        "session",
        "tls",
        "token",
    }
    parameters = {
        argument.arg
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    }

    assert not parameters & forbidden
    assert "serializeCompatibilityCallback" not in MODULE_PATH.read_text(encoding="utf-8")


def test_import_does_not_require_freecad_or_other_runtime_modules(monkeypatch) -> None:
    module_name = "phase12_isolated_collaboration_api"
    source = MODULE_PATH.read_text(encoding="utf-8")
    module = ModuleType(module_name)
    module.__file__ = str(MODULE_PATH)
    monkeypatch.setitem(sys.modules, module_name, module)

    exec(compile(source, str(MODULE_PATH), "exec"), module.__dict__)

    assert module.__all__ == ["CollaborationAPI"]
