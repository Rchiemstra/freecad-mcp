from __future__ import annotations

import FreeCAD
from tests.typed_feature_native_setup import prepare_native_document
from tests.typed_feature_native_matrix import collaborators
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.revolve_feature import run_revolve_feature

doc = FreeCAD.newDocument("RevDiag")
prepare_native_document(doc, "profile")
doc.recompute()
result = run_revolve_feature(
    collaborators(FreeCAD, lambda _d: None),
    doc.Name,
    "Sketch",
    "Revolve",
    360.0,
    "X_Axis",
    "Body",
)
print(result)
feat = doc.getObject("Revolve")
if feat is not None:
    shape = getattr(feat, "Shape", None)
    print("feat", feat.TypeId, tuple(feat.State), None if shape is None else shape.isNull())
FreeCAD.closeDocument(doc.Name)
