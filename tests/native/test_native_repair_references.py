"""Native qualification for typed ``repair_references``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    collaborators,
    load_runner,
    require_native_collaboration,
)

pytestmark = pytest.mark.core

_RUN_ARGS_MISSING = lambda _document, _ctx: (
    "MissingNativeDoc",
    [{"from": "Source", "to": "Target"}],
)


def _seed_link(document):
    source = document.addObject("App::FeaturePython", "Source")
    document.addObject("App::FeaturePython", "Target")
    link = document.addObject("App::Link", "Linker")
    link.LinkedObject = source
    document.recompute()
    return link


def _repairs():
    return [{"from": "Source", "to": "Target"}]


def test_repair_references_native_success_inspects_after_recompute(monkeypatch):
    require_native_collaboration()
    import FreeCAD

    subject, runner = load_runner("repair_references")
    document = FreeCAD.newDocument("MCPTypedrepair_references")
    doc_name = document.Name
    events: list[str] = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    try:
        _seed_link(document)
        probe = document.addObject("App::FeaturePython", "RecomputeProbe")
        probe.Proxy = RecomputeProbe()
        document.recompute()
        events.clear()

        original_apply = subject.apply_repair_references
        original_read = subject.read_repair_references_result

        def tracked_apply(admitted_document, *args, **kwargs):
            events.append("apply")
            receipt = original_apply(admitted_document, *args, **kwargs)
            probe.touch()
            return receipt

        def tracked_read(admitted_document, *args, **kwargs):
            events.append("inspect")
            return original_read(admitted_document, *args, **kwargs)

        monkeypatch.setattr(subject, "apply_repair_references", tracked_apply)
        monkeypatch.setattr(subject, "read_repair_references_result", tracked_read)
        result = runner(
            collaborators(FreeCAD, lambda _d: events.append("validate")),
            document.Name,
            _repairs(),
        )
        assert result["success"] is True, f"error_code={result.get('error_code')}: {result}"
        assert result["committed"] is True
        assert result["repaired_count"] >= 1
        assert events == ["apply", "recompute", "inspect", "validate"], (events, result)
        linker = document.getObject("Linker")
        target = document.getObject("Target")
        linked = getattr(linker, "LinkedObject", None)
        if isinstance(linked, tuple):
            linked = linked[0]
        assert linked is target
    finally:
        for name in list(FreeCAD.listDocuments()):
            if name.startswith("MCPTyped") or name == doc_name:
                try:
                    FreeCAD.closeDocument(name)
                except Exception:
                    pass


def test_repair_references_native_validation_failure_restores():
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("repair_references")
    document = FreeCAD.newDocument("MCPTypedrepair_referencesRollback")
    try:
        _seed_link(document)
        before_objects = tuple(obj.Name for obj in document.Objects)
        document.recompute()
        result = runner(
            collaborators(
                FreeCAD,
                lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
            ),
            document.Name,
            _repairs(),
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert tuple(obj.Name for obj in document.Objects) == before_objects
    finally:
        FreeCAD.closeDocument(document.Name)


def test_repair_references_native_missing_document_keeps_typed_error():
    check_missing_document("repair_references", _RUN_ARGS_MISSING)


def test_repair_references_native_missing_source_is_not_success():
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("repair_references")
    document = FreeCAD.newDocument("MCPTypedrepair_referencesMissingSrc")
    try:
        document.addObject("App::FeaturePython", "TypedBox")
        document.recompute()
        result = runner(
            collaborators(FreeCAD, lambda _d: None),
            document.Name,
            [{"from": "Missing", "to": "TypedBox"}],
        )
        assert result["success"] is False
        assert result["error_code"] == "OBJECT_NOT_FOUND"
    finally:
        FreeCAD.closeDocument(document.Name)
