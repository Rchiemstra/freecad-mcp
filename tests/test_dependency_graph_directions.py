"""get_dependency_graph must show both directions of a feature's links.

A stress run asked for the graph of a pocket ``Hole`` that four features
depended on: the result named only what ``Hole`` itself uses (and only via a
fixed list of property names), ``history_order`` was empty because ``Hole`` is
not a Body, and ``cycle_detected`` was hard-coded to false.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import diagnostics_shape_actions

pytestmark = pytest.mark.unit


class _Obj:
    def __init__(self, name, type_id="PartDesign::Feature", **links):
        self.Name = name
        self.TypeId = type_id
        self._links = dict(links)
        self.PropertiesList = ["Label", *links]
        self.InList: list[_Obj] = []
        self.OutList: list[_Obj] = []
        self.Group: list[_Obj] = []
        self.parent = None

    def __getattr__(self, name):
        links = self.__dict__.get("_links", {})
        if name in links:
            return links[name]
        raise AttributeError(name)

    def getTypeIdOfProperty(self, name):
        if name == "Label":
            return "App::PropertyString"
        value = self._links[name]
        if isinstance(value, list):
            return "App::PropertyLinkList"
        if isinstance(value, tuple):
            return "App::PropertyLinkSub"
        return "App::PropertyLink"

    def isDerivedFrom(self, type_id):
        return self.TypeId == type_id

    def getParentGeoFeatureGroup(self):
        return self.parent


def _link(source, target):
    source.OutList.append(target)
    target.InList.append(source)


def _document():
    plane = _Obj("XY_Plane", "App::Plane")
    sketch = _Obj("Sketch", "Sketcher::SketchObject")
    pad = _Obj("Pad", Profile=(sketch, ("",)))
    hole_sketch = _Obj("HoleSk", "Sketcher::SketchObject", AttachmentSupport=[(plane, ("",))])
    hole = _Obj("Hole", "PartDesign::Pocket", Profile=(hole_sketch, ("",)), BaseFeature=pad)
    mirror = _Obj("Mirror", "PartDesign::Mirrored", Originals=[hole])
    chamfer = _Obj("Chamfer", "PartDesign::Chamfer", Base=(mirror, ("Edge1", "Edge3")))
    body = _Obj("Body", "PartDesign::Body", Tip=chamfer)
    body.Group = [sketch, pad, hole_sketch, hole, mirror, chamfer]
    for feature in body.Group:
        feature.parent = body
        _link(body, feature)
    _link(body, chamfer)
    _link(pad, sketch)
    _link(hole_sketch, plane)
    _link(hole, hole_sketch)
    _link(hole, pad)
    _link(mirror, hole)
    _link(chamfer, mirror)
    objects = {obj.Name: obj for obj in (plane, body, *body.Group)}
    return SimpleNamespace(getObject=objects.get, Objects=list(objects.values()))


def _edges(graph):
    return {(edge["from"], edge["to"], edge["property"]) for edge in graph["edges"]}


def test_upstream_edges_follow_every_link_property():
    graph = diagnostics_shape_actions.get_dependency_graph(_document(), "Hole")

    assert _edges(graph) == {
        ("Hole", "HoleSk", "Profile"),
        ("Hole", "Pad", "BaseFeature"),
        ("HoleSk", "XY_Plane", "AttachmentSupport"),
        ("Pad", "Sketch", "Profile"),
    }


def test_subelements_are_reported_per_edge():
    graph = diagnostics_shape_actions.get_dependency_graph(_document(), "Chamfer")

    (edge,) = [item for item in graph["edges"] if item["from"] == "Chamfer"]
    assert edge["subelements"] == ["Edge1", "Edge3"]


def test_dependents_list_what_breaks_without_the_root():
    graph = diagnostics_shape_actions.get_dependency_graph(_document(), "Hole")

    assert graph["dependents"] == ["Mirror", "Chamfer"]


def test_a_feature_reports_its_body_history():
    graph = diagnostics_shape_actions.get_dependency_graph(_document(), "Hole")

    assert graph["history_order"] == ["Sketch", "Pad", "HoleSk", "Hole", "Mirror", "Chamfer"]


def test_a_link_cycle_is_detected():
    first = _Obj("A", Base=None)
    second = _Obj("B", Base=first)
    first._links["Base"] = second
    _link(first, second)
    _link(second, first)
    document = SimpleNamespace(getObject={"A": first, "B": second}.get)

    graph = diagnostics_shape_actions.get_dependency_graph(document, "A")

    assert graph["cycle_detected"] is True
