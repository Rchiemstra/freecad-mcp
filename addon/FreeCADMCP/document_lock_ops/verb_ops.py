from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from .verb_classification import VERB_CLASSIFICATION
from .verb_extractors import _params0_doc
from .verb_kind import VerbKind

_OBSCURING_CALLS = {
    "__import__",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "locals",
    "setattr",
    "vars",
}
_DOCUMENT_LIFECYCLE_CALLS = {
    "closeDocument",
    "newDocument",
    "open",
    "openDocument",
}


def classify_verb(method: str) -> tuple[VerbKind, Callable[[tuple], str | None]]:
    """Fail-closed: unknown verbs are MUTATING with params[0] doc extractor."""
    if method in VERB_CLASSIFICATION:
        return VERB_CLASSIFICATION[method]
    return VerbKind.MUTATING, _params0_doc


def extract_referenced_documents_from_code(code: str) -> set[str]:
    """Best-effort AST scan for FreeCAD.getDocument('Name') string literals."""
    names: set[str] = set()
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "getDocument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
        if (
            isinstance(func, ast.Name)
            and func.id == "getDocument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _validate_scope_node(node: ast.AST, violations: list[str], referenced: set[str]) -> None:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        violations.append(f"imports_not_allowed:{getattr(node, 'lineno', 0)}")
        return
    if isinstance(node, ast.Attribute) and node.attr == "ActiveDocument":
        violations.append(f"active_document_not_allowed:{getattr(node, 'lineno', 0)}")
        return
    if isinstance(node, ast.Name) and node.id == "ActiveDocument":
        violations.append(f"active_document_not_allowed:{getattr(node, 'lineno', 0)}")
        return
    if not isinstance(node, ast.Call):
        return
    func = node.func
    call_name = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr
        if isinstance(func, ast.Attribute)
        else ""
    )
    if call_name in _OBSCURING_CALLS:
        violations.append(
            f"dynamic_code_or_lookup_not_allowed:{call_name}:{getattr(node, 'lineno', 0)}"
        )
    if call_name in _DOCUMENT_LIFECYCLE_CALLS:
        violations.append(
            f"document_lifecycle_not_allowed:{call_name}:{getattr(node, 'lineno', 0)}"
        )
    if call_name != "getDocument":
        return
    if (
        not node.args
        or not isinstance(node.args[0], ast.Constant)
        or not isinstance(node.args[0].value, str)
    ):
        violations.append(
            f"dynamic_document_lookup_not_allowed:{getattr(node, 'lineno', 0)}"
        )
        return
    referenced.add(node.args[0].value)


def validate_unsafe_execute_scope(
    code: str, declared_documents: set[str]
) -> dict[str, Any]:
    """Conservatively validate explicitly enabled public live Python."""
    violations: list[str] = []
    referenced: set[str] = set()
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return {
            "ok": False,
            "referenced_documents": [],
            "violations": [f"syntax_error:{exc.lineno or 0}"],
        }

    for node in ast.walk(tree):
        _validate_scope_node(node, violations, referenced)

    undeclared = sorted(referenced - set(declared_documents))
    if undeclared:
        violations.append("undeclared_documents:" + ",".join(undeclared))
    return {
        "ok": not violations,
        "referenced_documents": sorted(referenced),
        "violations": sorted(set(violations)),
    }
