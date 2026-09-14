"""Shared native qualification matrix for lifecycle document ops."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

import pytest

from tests.core_doc_native_matrix import collaborators, load_runner, require_native_collaboration
from tests.core_doc_native_setup import prepare_core_document


def _install_admitted_probe(
    events: list[str],
    probe_holder: dict[str, object],
) -> Callable[[object], object]:
    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    def ensure_probe(admitted_document: object) -> object:
        if "probe" not in probe_holder:
            probe = admitted_document.addObject("App::FeaturePython", "RecomputeProbe")
            probe.Proxy = RecomputeProbe()
            probe_holder["probe"] = probe
        return probe_holder["probe"]

    return ensure_probe


def check_create_document_success(monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject, runner = load_runner("create_document")
    doc_name = "MCPCreateDocumentNativePhaseOrder"
    events: list[str] = []
    probe_holder: dict[str, object] = {}
    ensure_probe = _install_admitted_probe(events, probe_holder)

    original_apply = getattr(subject, "apply_create_document")
    original_read = getattr(subject, "read_create_document_result")

    def tracked_apply(admitted_document, request):
        events.append("apply")
        receipt = original_apply(admitted_document, request)
        for obj in getattr(admitted_document, "Objects", []) or []:
            if getattr(obj, "TypeId", "") == "App::FeaturePython":
                continue
            touch = getattr(obj, "touch", None)
            if callable(touch):
                touch()
                break
        else:
            ensure_probe(admitted_document).touch()
        return receipt

    def tracked_read(admitted_document, receipt):
        events.append("inspect")
        return original_read(admitted_document, receipt)

    monkeypatch.setattr(subject, "apply_create_document", tracked_apply)
    monkeypatch.setattr(subject, "read_create_document_result", tracked_read)
    try:
        result = runner(
            collaborators(FreeCAD, lambda _d: events.append("validate")),
            doc_name,
        )
        assert result["success"] is True
        assert result["committed"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)


def check_create_document_validation_failure() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("create_document")
    doc_name = "MCPCreateDocumentNativeRollback"
    admitted_holder: dict[str, Any] = {}

    original_new = FreeCAD.newDocument

    def capturing_new(name, *args, **kwargs):
        document = original_new(name, *args, **kwargs)
        if name == doc_name:
            admitted_holder["document"] = document
        return document

    FreeCAD.newDocument = capturing_new
    try:
        result = runner(
            collaborators(
                FreeCAD,
                lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
            ),
            doc_name,
        )
        assert admitted_holder.get("document") is not None
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert doc_name not in FreeCAD.listDocuments()
    finally:
        FreeCAD.newDocument = original_new
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)


def check_create_document_already_exists() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("create_document")
    existing = FreeCAD.newDocument("MCPExistingCreateDocument")
    try:
        result = runner(collaborators(FreeCAD, lambda _d: None), existing.Name)
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_ALREADY_EXISTS"
    finally:
        FreeCAD.closeDocument(existing.Name)


def check_open_document_success(monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject, runner = load_runner("open_document")
    fixture = FreeCAD.newDocument("MCPOpenDocumentFixture")
    try:
        ctx = prepare_core_document(fixture, "saved")
        path = ctx["path"]
        FreeCAD.closeDocument(fixture.Name)

        events: list[str] = []
        probe_holder: dict[str, object] = {}
        ensure_probe = _install_admitted_probe(events, probe_holder)

        original_apply = getattr(subject, "apply_open_document")
        original_read = getattr(subject, "read_open_document_result")

        def tracked_apply(admitted_document, request):
            events.append("apply")
            receipt = original_apply(admitted_document, request)
            for obj in getattr(admitted_document, "Objects", []) or []:
                if getattr(obj, "TypeId", "") == "App::FeaturePython":
                    continue
                touch = getattr(obj, "touch", None)
                if callable(touch):
                    touch()
                    break
            else:
                ensure_probe(admitted_document).touch()
            return receipt

        def tracked_read(admitted_document, receipt):
            events.append("inspect")
            return original_read(admitted_document, receipt)

        monkeypatch.setattr(subject, "apply_open_document", tracked_apply)
        monkeypatch.setattr(subject, "read_open_document_result", tracked_read)
        opened_name: str | None = None
        try:
            result = runner(
                collaborators(FreeCAD, lambda _d: events.append("validate")),
                path,
            )
            assert result["success"] is True
            assert result["committed"] is True
            assert events == ["apply", "recompute", "inspect", "validate"]
            candidate = result.get("document_name")
            opened_name = candidate if isinstance(candidate, str) else None
        finally:
            if opened_name and opened_name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(opened_name)
    finally:
        for name in list(FreeCAD.listDocuments()):
            if name in {fixture.Name, "MCPOpenDocumentFixture"}:
                try:
                    FreeCAD.closeDocument(name)
                except Exception:
                    pass


def check_open_document_validation_failure() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("open_document")
    fixture = FreeCAD.newDocument("MCPOpenDocumentRollbackFixture")
    admitted_holder: dict[str, Any] = {}
    opened_name: str | None = None
    original_open = FreeCAD.openDocument

    def capturing_open(path, *args, **kwargs):
        document = original_open(path, *args, **kwargs)
        admitted_holder["document"] = document
        admitted_holder["before_objects"] = tuple(obj.Name for obj in document.Objects)
        return document

    try:
        ctx = prepare_core_document(fixture, "saved")
        path = ctx["path"]
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.openDocument = capturing_open
        result = runner(
            collaborators(
                FreeCAD,
                lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
            ),
            path,
        )
        admitted = admitted_holder.get("document")
        assert admitted is not None
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert tuple(obj.Name for obj in admitted.Objects) == admitted_holder["before_objects"]
        opened_name = admitted.Name
    finally:
        FreeCAD.openDocument = original_open
        if opened_name and opened_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(opened_name)


def check_open_document_missing_path() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("open_document")
    result = runner(
        collaborators(FreeCAD, lambda _d: None),
        "/no/such/document.FCStd",
    )
    assert result["success"] is False
    assert result["error_code"] == "OPEN_DOCUMENT_FAILED"
