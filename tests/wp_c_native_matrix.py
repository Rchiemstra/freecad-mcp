"""Native qualification helpers for WP-C policy ops."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from tests.assembly_io_native_setup import prepare_assembly_document
from tests.core_doc_native_matrix import collaborators, load_runner, require_native_collaboration

_EXPORT_SUFFIX = {
    "export_step": ".step",
    "export_stl": ".stl",
    "export_brep": ".brep",
}


def wp_c_collaborators(FreeCAD, validator, **extras):
    collab = collaborators(FreeCAD, validator)
    for key, value in extras.items():
        setattr(collab, key, value)
    return collab


def check_history_success(op: str, kind: str) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    document = FreeCAD.newDocument(f"MCP{op}NativeVerified")
    doc_name = document.Name
    try:
        document.openTransaction("MCPHistoryNative")
        document.addObject("App::FeaturePython", "HistoryProbe")
        document.commitTransaction()
        if op == "redo":
            document.undo()
        result = runner(collaborators(FreeCAD, lambda _d: None), doc_name)
        assert result["success"] is True
        assert result["outcome"] == "verified"
        assert doc_name in FreeCAD.listDocuments()
    finally:
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)


def check_history_missing(op: str) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    result = runner(collaborators(FreeCAD, lambda _d: None), "MissingNativeDoc")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def check_query_success(op: str, kind: str, run_args: Callable[[str, dict[str, str]], tuple]) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    document = FreeCAD.newDocument(f"MCP{op}NativeObserved")
    doc_name = document.Name
    try:
        ctx = prepare_assembly_document(document, kind)
        document.recompute()
        result = runner(collaborators(FreeCAD, lambda _d: None), *run_args(doc_name, ctx))
        assert result["success"] is True
        assert result["outcome"] == "observed"
    finally:
        FreeCAD.closeDocument(doc_name)


def check_query_missing(op: str, run_args: Callable[[str, dict[str, str]], tuple]) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    result = runner(collaborators(FreeCAD, lambda _d: None), *run_args("MissingNativeDoc", {"box": "Box"}))
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def check_export_success(op: str, kind: str, run_args: Callable[[str, dict[str, str], Path], tuple]) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    document = FreeCAD.newDocument(f"MCP{op}NativePublished")
    doc_name = document.Name
    suffix = _EXPORT_SUFFIX[op]
    try:
        ctx = prepare_assembly_document(document, kind)
        document.recompute()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / f"part{suffix}"
            staged = dest.with_name(f"{dest.stem}.tmp{dest.suffix}")
            result = runner(
                collaborators(FreeCAD, lambda _d: None),
                *run_args(doc_name, ctx, dest),
            )
            assert result["success"] is True
            assert result["outcome"] == "published"
            assert dest.is_file()
            assert not staged.exists()
    finally:
        FreeCAD.closeDocument(doc_name)


def check_export_missing(op: str, run_args: Callable[[str, dict[str, str], Path], tuple]) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    suffix = _EXPORT_SUFFIX.get(op, ".out")
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / f"missing{suffix}"
        result = runner(
            collaborators(FreeCAD, lambda _d: None),
            *run_args("MissingNativeDoc", {"box": "Box"}, dest),
        )
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
