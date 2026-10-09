"""A FEM run with no mesh must fail before it adds a solver."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.fem_executor_ops import run_analysis

pytestmark = pytest.mark.unit


def test_missing_mesh_is_reported_without_creating_a_solver(monkeypatch):
    analysis = SimpleNamespace(Name="Analysis", TypeId="Fem::FemAnalysis", Group=[])
    document = SimpleNamespace(getObject=lambda name: analysis if name == "Analysis" else None)
    monkeypatch.setattr(run_analysis.FreeCAD, "getDocument", lambda _name: document)
    monkeypatch.setattr(
        run_analysis,
        "resolve_solver",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("solver created")),
    )

    result = run_analysis.run_fem_analysis("Doc", "Analysis")

    assert result["success"] is False
    assert "mesh" in result["error"].lower()
    assert analysis.Group == []
