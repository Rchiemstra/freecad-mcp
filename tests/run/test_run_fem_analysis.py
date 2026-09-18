"""Unit coverage for the typed ``run_fem_analysis`` external-effect slice."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import run_fem_analysis as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import run_run_fem_analysis

pytestmark = pytest.mark.unit


def test_run_fem_analysis_published_without_native_mutation():
    events: list[str] = []
    analysis = SimpleNamespace(Name="Analysis", Label="Analysis")
    document = SimpleNamespace(
        Name="Doc",
        getObject=lambda name: analysis if name == "Analysis" else None,
    )
    collab = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        run_fem_analysis=lambda *_args, **_kwargs: {"success": True},
    )
    with patch.object(subject, "_ensure_fem_mesh"):
        result = run_run_fem_analysis(collab, "Doc", "Analysis", 600)

    assert result["success"] is True
    assert result["outcome"] == "published"
    assert "commit" not in events


def test_missing_document_is_rejected():
    collab = SimpleNamespace(freecad=SimpleNamespace(getDocument=lambda _name: None))

    result = run_run_fem_analysis(collab, "Doc", "Analysis", 600)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_analysis_is_rejected():
    document = SimpleNamespace(Name="Doc", getObject=lambda _name: None)
    collab = SimpleNamespace(freecad=SimpleNamespace(getDocument=lambda _name: document))

    result = run_run_fem_analysis(collab, "Doc", "Analysis", 600)

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"


def test_gmsh_failed_after_mesh_start_skips_to_solver_when_collaborator_present():
    document = SimpleNamespace(
        Name="Doc",
        Objects=[],
        getObject=lambda name: SimpleNamespace(Name=name, Group=[], Proxy=None, TypeId=""),
    )
    collab = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        run_fem_analysis=lambda *_a, **_k: {"success": True},
    )
    with patch.object(subject, "_ensure_fem_mesh", side_effect=subject.RunFemAnalysisError("GMSH_FAILED", "mesh broke")):
        result = run_run_fem_analysis(collab, "Doc", "Analysis", 600)

    assert result["success"] is True
    assert result["outcome"] == "published"


def test_gmsh_failed_after_mesh_start_is_uncertain_without_solver_collaborator():
    document = SimpleNamespace(
        Name="Doc",
        Objects=[],
        getObject=lambda name: SimpleNamespace(Name=name, Group=[], Proxy=None, TypeId=""),
    )
    collab = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
    )
    with patch.object(subject, "_ensure_fem_mesh", side_effect=subject.RunFemAnalysisError("GMSH_FAILED", "mesh broke")):
        result = run_run_fem_analysis(collab, "Doc", "Analysis", 600)

    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "GMSH_FAILED"
