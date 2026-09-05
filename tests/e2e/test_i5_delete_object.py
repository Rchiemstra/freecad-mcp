"""I5 e2e: delete_object refuses to silently orphan dependents and, with
recursive=True, removes them too — against a live FreeCAD (P6 guardrail).

A PartDesign Body with a padded circle has the sketch and pad as dependents.
  * Bare delete  -> refused, dependents listed (no orphaning).
  * recursive    -> sketch, pad and body all removed.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.core import delete_object_operation  # noqa: E402
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_mutation import (  # noqa: E402
    run_cad_mutation,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.object_crud import (  # noqa: E402
    delete_object_gui,
)
from tests.e2e._helpers import make_padded_circle, tool_response_text  # noqa: E402

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = tool_response_text(response)
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    # Recompute progress noise can surround the payload line, so scan from the
    # end for the first line that parses as JSON instead of trusting a fixed
    # line position.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON payload line in response text: {text!r}")


def test_delete_refuses_and_lists_dependents(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Horn")
    sk, pad = make_padded_circle(body, radius=2, length=1, plane_label="XY_Plane")

    resp = delete_object_operation(freecad_session, True, doc.Name, body.Name)
    payload = _payload(resp)

    assert payload["ok"] is True
    assert payload["refused"] is True
    dep_names = {d["name"] for d in payload["dependents"]}
    assert sk.Name in dep_names
    assert pad.Name in dep_names
    # Nothing was actually deleted.
    remaining = {o.Name for o in doc.Objects}
    assert body.Name in remaining and sk.Name in remaining and pad.Name in remaining


def test_delete_recursive_removes_dependents(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Horn")
    sk, pad = make_padded_circle(body, radius=2, length=1, plane_label="XY_Plane")
    body_name = body.Name
    gone = {body.Name, sk.Name, pad.Name}

    resp = delete_object_operation(
        freecad_session,
        True,
        doc.Name,
        body.Name,
        recursive=True,
    )
    payload = _payload(resp)

    assert payload["ok"] is True
    assert payload["refused"] is False
    assert body_name in payload["deleted"]
    remaining = {o.Name for o in doc.Objects}
    assert not (remaining & gone), f"orphans left: {remaining & gone}"


def test_partially_completed_recursive_delete_restores_status_and_readiness(
    freecad_session,
):
    doc = freecad_session.doc
    root = doc.addObject("App::DocumentObjectGroup", "DeleteRoot")
    child_a = doc.addObject("Part::Feature", "DeleteChildA")
    child_b = doc.addObject("Part::Feature", "DeleteChildB")
    root.addObject(child_a)
    root.addObject(child_b)
    doc.recompute()

    names_before = [obj.Name for obj in doc.Objects]
    status_before = {
        obj.Name: {
            "state": tuple(str(item) for item in obj.State),
            "must_execute": bool(obj.MustExecute),
        }
        for obj in doc.Objects
    }
    readiness_before = dict(doc.getMutationReadiness())
    assert readiness_before["ready"] is True
    remove_calls = []

    class FailingDocumentProxy:
        def __getattr__(self, name):
            return getattr(doc, name)

        def removeObject(self, name):
            remove_calls.append(name)
            if len(remove_calls) == 2:
                raise RuntimeError("injected failure after one successful removal")
            return doc.removeObject(name)

    document_proxy = FailingDocumentProxy()

    class FreeCADProxy:
        Console = FreeCAD.Console

        @staticmethod
        def getDocument(name):
            return document_proxy if name == doc.Name else FreeCAD.getDocument(name)

        def __getattr__(self, name):
            return getattr(FreeCAD, name)

    freecad_proxy = FreeCADProxy()
    collaborators = replace(
        freecad_session._rpc._cad_collaborators,
        freecad=freecad_proxy,
    )

    result = run_cad_mutation(
        collaborators,
        doc.Name,
        lambda: delete_object_gui(
            doc.Name,
            root.Name,
            freecad=freecad_proxy,
            recursive=True,
        ),
        structural=True,
        method="delete_object",
    )

    assert result["success"] is False
    assert result["error_code"] == "DELETE_OBJECT_FAILED"
    assert len(remove_calls) >= 2
    assert [obj.Name for obj in doc.Objects] == names_before
    assert {
        obj.Name: {
            "state": tuple(str(item) for item in obj.State),
            "must_execute": bool(obj.MustExecute),
        }
        for obj in doc.Objects
    } == status_before
    readiness_after = dict(doc.getMutationReadiness())
    assert readiness_after["ready"] is True
    assert readiness_after["must_execute"] is False
    assert readiness_after == readiness_before
