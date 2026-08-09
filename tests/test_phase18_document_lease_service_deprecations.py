"""Phase 18 contracts for the frozen document-lease service adapters."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers.architecture_baseline import (
    FROZEN_DEPRECATION_RESULT,
    load_manifest,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE_MODULE = "addon.FreeCADMCP.document_lease.service"
SERVICE_INSTALLED_MODULE = "document_lease.service"
FACADE_MODULE = "addon.FreeCADMCP.document_lease.service_ops.facade_bindings"
FACADE_INSTALLED_MODULE = "document_lease.service_ops.facade_bindings"
SERVICE_PATH = ROOT / "addon/FreeCADMCP/document_lease/service.py"
FACADE_PATH = (
    ROOT / "addon/FreeCADMCP/document_lease/service_ops/facade_bindings.py"
)
MODULE_CASES = (
    (SERVICE_MODULE, SERVICE_INSTALLED_MODULE, SERVICE_PATH),
    (FACADE_MODULE, FACADE_INSTALLED_MODULE, FACADE_PATH),
)

EXPECTED_DEFAULTS = {
    SERVICE_MODULE: {
        "DocumentLeaseService": {
            "sidecar_store": None,
            "token_factory": ("callable", "<lambda>"),
            "uuid_factory": ("callable", "uuid4"),
            "utc_clock": ("callable", "utc_now"),
            "monotonic_ns": ("callable", "monotonic_ns"),
            "sidecar_heartbeat_interval_seconds": 30.0,
            "stale_after_seconds": 90.0,
            "local_runtime_identity": None,
            "process_liveness_probe": None,
        }
    },
    FACADE_MODULE: {
        "claim_locked_error_handoff": {"task_summary": ""},
        "recover_orphaned_local_mcp_acquisition": {
            "task_summary": "",
            "authority_handoff": None,
            "authority_rollback": None,
            "credential_escrow": None,
        },
    },
}

EXPECTED_DEFAULT_TYPES = {
    SERVICE_MODULE: {
        "DocumentLeaseService": {
            "sidecar_store": "NoneType",
            "token_factory": "function",
            "uuid_factory": "function",
            "utc_clock": "function",
            "monotonic_ns": "builtin_function_or_method",
            "sidecar_heartbeat_interval_seconds": "float",
            "stale_after_seconds": "float",
            "local_runtime_identity": "NoneType",
            "process_liveness_probe": "NoneType",
        }
    },
    FACADE_MODULE: {
        "claim_locked_error_handoff": {"task_summary": "str"},
        "recover_orphaned_local_mcp_acquisition": {
            "task_summary": "str",
            "authority_handoff": "NoneType",
            "authority_rollback": "NoneType",
            "credential_escrow": "NoneType",
        },
    },
}

EXPECTED_ANNOTATIONS = {
    SERVICE_MODULE: {
        "DocumentLeaseService": {
            "identity_service": "DocumentIdentityService",
            "sidecar_store": "SidecarStore | None",
            "token_factory": "Callable[[], str]",
            "uuid_factory": "Callable[[], uuid.UUID | str]",
            "utc_clock": "Callable[[], str]",
            "monotonic_ns": "Callable[[], int]",
            "sidecar_heartbeat_interval_seconds": "float",
            "stale_after_seconds": "float",
            "local_runtime_identity": "LocalRuntimeIdentity | None",
            "process_liveness_probe": (
                "Callable[[int], ProcessLivenessEvidence] | None"
            ),
            "return": "dict[str, object]",
        }
    },
    FACADE_MODULE: {
        "claim_locked_error_handoff": {
            "selector": "DocumentSelector | Mapping[str, Any] | str",
            "owner": "LeaseOwner",
            "validation": "LiveDocumentValidation",
            "local_confirmation": "bool",
            "task_summary": "str",
            "return": "dict[str, object]",
        },
        "recover_orphaned_local_mcp_acquisition": {
            "selector": "DocumentSelector | Mapping[str, Any] | str",
            "owner": "LeaseOwner",
            "validation": "LiveDocumentValidation",
            "snapshot_id": "str",
            "task_summary": "str",
            "authority_handoff": "Callable[[LeaseRecord], bool] | None",
            "authority_rollback": "Callable[[], bool] | None",
            "credential_escrow": "Callable[[LeaseGrant], bool] | None",
            "return": "dict[str, object]",
        },
        "release_clean": {
            "credential": "LeaseCredential",
            "validation": "LiveDocumentValidation",
            "return": "dict[str, Any]",
        },
    },
}

EXPECTED_FUNCTIONS = {
    SERVICE_PATH: (
        "_legacy_lease_authority_removed",
        "utc_now",
        "DocumentLeaseService",
    ),
    FACADE_PATH: (
        "_legacy_lease_authority_removed",
        "claim_locked_error_handoff",
        "recover_orphaned_local_mcp_acquisition",
        "release_clean",
    ),
}

EXPECTED_IMPORTS = {
    SERVICE_PATH: (
        ("__future__", ("annotations",)),
        (None, ("secrets",)),
        (None, ("time",)),
        (None, ("uuid",)),
        ("collections.abc", ("Callable",)),
        ("datetime", ("UTC", "datetime")),
    ),
    FACADE_PATH: (
        ("__future__", ("annotations",)),
        ("collections.abc", ("Callable", "Mapping")),
        ("typing", ("Any",)),
    ),
}


def _surface(module_name: str) -> dict[str, object]:
    return next(
        surface
        for surface in load_manifest()["retained_compatibility_surfaces"]
        if surface["module"] == module_name
    )


def _contract(value: object) -> list[dict[str, object]]:
    return [
        {
            "name": parameter.name,
            "kind": parameter.kind.name.lower(),
            "required": parameter.default is inspect.Parameter.empty,
        }
        for parameter in inspect.signature(value).parameters.values()
    ]


def _normalized_default(value: object) -> object:
    if callable(value):
        return ("callable", value.__name__)
    return value


def _defaults(value: object) -> dict[str, object]:
    return {
        parameter.name: _normalized_default(parameter.default)
        for parameter in inspect.signature(value).parameters.values()
        if parameter.default is not inspect.Parameter.empty
    }


def _default_types(value: object) -> dict[str, str]:
    return {
        parameter.name: type(parameter.default).__name__
        for parameter in inspect.signature(value).parameters.values()
        if parameter.default is not inspect.Parameter.empty
    }


def _annotations(value: object) -> dict[str, object]:
    signature = inspect.signature(value)
    result = {
        parameter.name: parameter.annotation
        for parameter in signature.parameters.values()
        if parameter.annotation is not inspect.Parameter.empty
    }
    if signature.return_annotation is not inspect.Signature.empty:
        result["return"] = signature.return_annotation
    return result


def _representative_call(
    value: object,
    contract: list[dict[str, object]],
) -> dict[str, object]:
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for parameter in contract:
        if not parameter["required"]:
            continue
        if parameter["kind"] == "positional_or_keyword":
            args.append(object())
        elif parameter["kind"] == "keyword_only":
            kwargs[str(parameter["name"])] = object()
        else:  # pragma: no cover - neither frozen surface uses another kind
            raise AssertionError(f"unexpected parameter kind: {parameter['kind']}")
    return value(*args, **kwargs)


@contextmanager
def _isolated_import_spellings(addon_name: str, installed_name: str):
    bootstrap_unit_test_runtime()
    installed_addon_root = str(ROOT / "addon" / "FreeCADMCP")
    added_path = installed_addon_root not in sys.path
    if added_path:
        sys.path.insert(0, installed_addon_root)

    try:
        with patch.dict(sys.modules):
            sys.modules.pop(addon_name, None)
            sys.modules.pop(installed_name, None)
            yield (
                importlib.import_module(addon_name),
                importlib.import_module(installed_name),
            )
    finally:
        if added_path:
            sys.path.remove(installed_addon_root)


@pytest.mark.parametrize(
    ("module_name", "installed_name", "module_path"),
    MODULE_CASES,
)
def test_manifest_names_exact_defaults_and_annotations_are_preserved(
    module_name: str,
    installed_name: str,
    module_path: Path,
):
    surface = _surface(module_name)
    contracts = {
        item["symbol"]: item["parameter_contract"]
        for item in surface["post_cutover_deprecation_contracts"]
    }

    assert list(contracts) == surface["current_symbols"]
    with _isolated_import_spellings(module_name, installed_name) as modules:
        for module in modules:
            assert Path(module.__file__).resolve() == module_path.resolve()
            assert list(module.__all__) == surface["current_symbols"]
            observed_defaults = {}
            observed_default_types = {}
            observed_annotations = {}
            for name, expected_contract in contracts.items():
                value = getattr(module, name)
                assert _contract(value) == expected_contract
                if defaults := _defaults(value):
                    observed_defaults[name] = defaults
                    observed_default_types[name] = _default_types(value)
                if annotations := _annotations(value):
                    observed_annotations[name] = annotations
            assert observed_defaults == EXPECTED_DEFAULTS[module_name]
            assert observed_default_types == EXPECTED_DEFAULT_TYPES[module_name]
            assert observed_annotations == EXPECTED_ANNOTATIONS[module_name]


@pytest.mark.parametrize(
    ("module_name", "installed_name", "module_path"),
    MODULE_CASES,
)
def test_every_adapter_call_returns_a_fresh_exact_result(
    module_name: str,
    installed_name: str,
    module_path: Path,
):
    del module_path
    surface = _surface(module_name)
    contracts = {
        item["symbol"]: item["parameter_contract"]
        for item in surface["post_cutover_deprecation_contracts"]
    }

    with _isolated_import_spellings(module_name, installed_name) as modules:
        for module in modules:
            for name, contract in contracts.items():
                value = getattr(module, name)
                first = _representative_call(value, contract)
                second = _representative_call(value, contract)

                assert first == FROZEN_DEPRECATION_RESULT
                assert second == FROZEN_DEPRECATION_RESULT
                assert first is not second
                first["success"] = "mutated"
                assert second == FROZEN_DEPRECATION_RESULT


@pytest.mark.parametrize(
    ("module_name", "installed_name", "module_path"),
    MODULE_CASES,
)
def test_supported_import_spellings_are_isolated_and_resolve_the_leaf_source(
    module_name: str,
    installed_name: str,
    module_path: Path,
):
    before = {
        name: sys.modules.get(name)
        for name in (module_name, installed_name)
    }
    with _isolated_import_spellings(module_name, installed_name) as modules:
        addon_module, installed_module = modules
        assert Path(addon_module.__file__).resolve() == module_path.resolve()
        assert Path(installed_module.__file__).resolve() == module_path.resolve()
        assert addon_module is not installed_module
        for name in _surface(module_name)["current_symbols"]:
            addon_callable = getattr(addon_module, name)
            installed_callable = getattr(installed_module, name)
            assert addon_callable is not installed_callable
            assert addon_callable.__name__ == installed_callable.__name__ == name

    assert {
        name: sys.modules.get(name)
        for name in (module_name, installed_name)
    } == before


def _without_docstring(function: ast.FunctionDef) -> list[ast.stmt]:
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ):
        body.pop(0)
    return body


def _import_contract(node: ast.Import | ast.ImportFrom):
    assert all(alias.asname is None for alias in node.names)
    if isinstance(node, ast.Import):
        return None, tuple(alias.name for alias in node.names)
    return node.module, tuple(alias.name for alias in node.names)


def _assert_default_is_side_effect_free(default: ast.expr) -> None:
    assert isinstance(default, (ast.Constant, ast.Name, ast.Attribute, ast.Lambda))
    if not isinstance(default, ast.Lambda):
        assert not any(isinstance(node, ast.Call) for node in ast.walk(default))
        return

    assert not default.args.args
    assert isinstance(default.body, ast.Call)
    assert isinstance(default.body.func, ast.Attribute)
    assert isinstance(default.body.func.value, ast.Name)
    assert (default.body.func.value.id, default.body.func.attr) == (
        "secrets",
        "token_urlsafe",
    )
    assert len(default.body.args) == 1
    assert isinstance(default.body.args[0], ast.Constant)
    assert default.body.args[0].value == 32
    assert not default.body.keywords


def _assert_function_body_is_pure(function: ast.FunctionDef) -> None:
    assert not function.decorator_list
    defaults = [*function.args.defaults]
    defaults.extend(
        default
        for default in function.args.kw_defaults
        if default is not None
    )
    for default in defaults:
        _assert_default_is_side_effect_free(default)

    body = _without_docstring(function)
    if function.name == "_legacy_lease_authority_removed":
        assert len(body) == 1
        assert isinstance(body[0], ast.Return)
        assert isinstance(body[0].value, ast.Dict)
        assert ast.literal_eval(body[0].value) == FROZEN_DEPRECATION_RESULT
        return
    if function.name == "utc_now":
        assert len(body) == 1
        assert isinstance(body[0], ast.Return)
        expected = ast.parse(
            "datetime.now(UTC).isoformat(timespec='milliseconds')"
            ".replace('+00:00', 'Z')",
            mode="eval",
        )
        assert ast.dump(body[0].value, include_attributes=False) == ast.dump(
            expected.body,
            include_attributes=False,
        )
        return

    assert len(body) == 2
    assert isinstance(body[0], ast.Delete)
    deleted_names = tuple(
        child.id
        for target in body[0].targets
        for child in ast.walk(target)
        if isinstance(child, ast.Name)
    )
    parameter_names = tuple(
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
    )
    assert deleted_names == parameter_names
    assert isinstance(body[1], ast.Return)
    assert isinstance(body[1].value, ast.Call)
    assert isinstance(body[1].value.func, ast.Name)
    assert body[1].value.func.id == "_legacy_lease_authority_removed"
    assert not body[1].value.args
    assert not body[1].value.keywords


@pytest.mark.parametrize("module_path", (SERVICE_PATH, FACADE_PATH))
def test_deprecation_modules_are_static_stateless_leaf_adapters(module_path: Path):
    tree = ast.parse(
        module_path.read_text(encoding="utf-8"),
        filename=str(module_path),
    )
    allowed_top_level = (
        ast.Expr,
        ast.Import,
        ast.ImportFrom,
        ast.Assign,
        ast.FunctionDef,
    )
    assert all(isinstance(node, allowed_top_level) for node in tree.body)
    expressions = [node for node in tree.body if isinstance(node, ast.Expr)]
    assert len(expressions) == 1
    assert expressions[0] is tree.body[0]
    assert isinstance(expressions[0].value, ast.Constant)
    assert isinstance(expressions[0].value.value, str)

    imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert tuple(_import_contract(node) for node in imports) == EXPECTED_IMPORTS[
        module_path
    ]

    assignments = [node for node in tree.body if isinstance(node, ast.Assign)]
    assert len(assignments) == 1
    assert len(assignments[0].targets) == 1
    assert isinstance(assignments[0].targets[0], ast.Name)
    assert assignments[0].targets[0].id == "__all__"
    assert isinstance(assignments[0].value, ast.Tuple)
    assert all(
        isinstance(element, ast.Constant)
        and isinstance(element.value, str)
        for element in assignments[0].value.elts
    )

    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert tuple(function.name for function in functions) == EXPECTED_FUNCTIONS[
        module_path
    ]
    for function in functions:
        _assert_function_body_is_pure(function)

    assert not any(
        isinstance(
            node,
            (
                ast.AsyncFunctionDef,
                ast.AsyncWith,
                ast.AugAssign,
                ast.ClassDef,
                ast.Global,
                ast.NamedExpr,
                ast.Nonlocal,
                ast.With,
            ),
        )
        for node in ast.walk(tree)
    )
    forbidden_calls = {
        "__import__",
        "eval",
        "exec",
        "getattr",
        "globals",
        "locals",
        "setattr",
    }
    assert not any(
        isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id in forbidden_calls
            or isinstance(node.func, ast.Attribute)
            and node.func.attr in {"import_module", "reload"}
        )
        for node in ast.walk(tree)
    )
