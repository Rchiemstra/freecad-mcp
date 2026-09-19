"""Behavioral tests for shared world-frame shape resolution (phase-3a)."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    diagnostics_shape_actions,
    world_shape_actions,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.bounding_box import (
    run_bounding_box,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.measure_volume import (
    run_measure_volume,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_runtime import (
    TypedMutationError,
)
from tests.helpers.geometric import assert_bbox, assert_code_contains, assert_volume
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit

_CUBE_SIZE = 10.0


class FakeVector:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class FakeRotation:
    def __init__(self, axis: FakeVector | None = None, angle: float = 0.0) -> None:
        self.Axis = axis or FakeVector(0.0, 0.0, 1.0)
        self.Angle = float(angle)


class FakeMatrix:
    def __init__(
        self,
        *,
        translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
        angle_z: float = 0.0,
    ) -> None:
        self._translation = translation
        self._scale = scale
        self._angle_z = angle_z

    @classmethod
    def from_placement(cls, placement: FakePlacement) -> FakeMatrix:
        return cls(
            translation=(placement.Base.x, placement.Base.y, placement.Base.z),
            angle_z=float(getattr(placement.Rotation, "Angle", 0.0)),
        )

    def scale(self, sx: float, sy: float, sz: float) -> None:
        self._scale = (
            self._scale[0] * sx,
            self._scale[1] * sy,
            self._scale[2] * sz,
        )

    def apply_point(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        sx, sy, sz = self._scale
        tx, ty, tz = self._translation
        rx = x * sx
        ry = y * sy
        if self._angle_z:
            c = math.cos(self._angle_z)
            s = math.sin(self._angle_z)
            rx, ry = rx * c - ry * s, rx * s + ry * c
        return rx + tx, ry + ty, z * sz + tz

    def toMatrix(self) -> FakeMatrix:
        return FakeMatrix(
            translation=self._translation,
            scale=self._scale,
            angle_z=self._angle_z,
        )

    def __mul__(self, other: FakeMatrix) -> FakeMatrix:
        left = self
        right = other if isinstance(other, FakeMatrix) else FakeMatrix()
        composed = FakeMatrix(
            translation=left.apply_point(*right._translation),
            scale=(
                left._scale[0] * right._scale[0],
                left._scale[1] * right._scale[1],
                left._scale[2] * right._scale[2],
            ),
            angle_z=left._angle_z + right._angle_z,
        )
        return composed


class FakePlacement:
    def __init__(
        self,
        base: FakeVector | None = None,
        rotation: FakeRotation | None = None,
    ) -> None:
        self.Base = base or FakeVector()
        self.Rotation = rotation or FakeRotation()

    def toMatrix(self) -> FakeMatrix:
        return FakeMatrix.from_placement(self)

    def __mul__(self, other: FakePlacement) -> FakePlacement:
        left = self.toMatrix()
        right = other.toMatrix()
        composed = left * right
        return FakePlacement(
            base=FakeVector(*composed._translation),
            rotation=FakeRotation(angle=composed._angle_z),
        )


class FakeBoundBox:
    def __init__(
        self,
        xmin: float,
        ymin: float,
        zmin: float,
        xmax: float,
        ymax: float,
        zmax: float,
    ) -> None:
        self.XMin = xmin
        self.YMin = ymin
        self.ZMin = zmin
        self.XMax = xmax
        self.YMax = ymax
        self.ZMax = zmax
        self.XLength = xmax - xmin
        self.YLength = ymax - ymin
        self.ZLength = zmax - zmin
        self.DiagonalLength = math.sqrt(self.XLength**2 + self.YLength**2 + self.ZLength**2)


class UnitCubeShape:
    """10 mm cube oracle; transformShape applies a FakeMatrix once.

    As in FreeCAD, an object's Shape already carries that object's own Placement: build a
    placed feature's cube with the same translation/rotation (D-30).
    """

    def __init__(
        self,
        *,
        translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
        angle_z: float = 0.0,
    ) -> None:
        self._matrix = FakeMatrix(translation=translation, scale=scale, angle_z=angle_z)
        self.Faces = [object()] * 6
        self.Edges = [object()] * 12
        self.Vertexes = [object()] * 8

    def isNull(self) -> bool:
        return False

    def copy(self) -> UnitCubeShape:
        matrix = self._matrix
        return UnitCubeShape(
            translation=matrix._translation,
            scale=matrix._scale,
            angle_z=matrix._angle_z,
        )

    def transformShape(self, matrix: FakeMatrix) -> None:
        corners = [
            self._matrix.apply_point(x, y, z)
            for x in (0.0, _CUBE_SIZE)
            for y in (0.0, _CUBE_SIZE)
            for z in (0.0, _CUBE_SIZE)
        ]
        transformed = [matrix.apply_point(*point) for point in corners]
        xs = [point[0] for point in transformed]
        ys = [point[1] for point in transformed]
        zs = [point[2] for point in transformed]
        self._bound_box = FakeBoundBox(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        sx, sy, sz = matrix._scale
        self._volume = _CUBE_SIZE**3 * sx * sy * sz
        anchor = matrix.apply_point(*self._matrix._translation)
        self._matrix = FakeMatrix(
            translation=anchor,
            scale=(
                self._matrix._scale[0] * sx,
                self._matrix._scale[1] * sy,
                self._matrix._scale[2] * sz,
            ),
            angle_z=self._matrix._angle_z + matrix._angle_z,
        )

    @property
    def BoundBox(self) -> FakeBoundBox:
        if hasattr(self, "_bound_box"):
            return self._bound_box
        matrix = self._matrix
        corners = [
            matrix.apply_point(x, y, z)
            for x in (0.0, _CUBE_SIZE)
            for y in (0.0, _CUBE_SIZE)
            for z in (0.0, _CUBE_SIZE)
        ]
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        zs = [point[2] for point in corners]
        return FakeBoundBox(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    @property
    def Volume(self) -> float:
        if hasattr(self, "_volume"):
            return self._volume
        sx, sy, sz = self._matrix._scale
        return _CUBE_SIZE**3 * sx * sy * sz


class NullShape:
    def isNull(self) -> bool:
        return True


class MeasureObject(SimpleNamespace):
    pass


def _analytic_bbox(
    *,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    angle_z: float = 0.0,
) -> tuple[float, float, float, float, float, float]:
    matrix = FakeMatrix(translation=translation, scale=scale, angle_z=angle_z)
    corners = [
        matrix.apply_point(x, y, z)
        for x in (0.0, _CUBE_SIZE)
        for y in (0.0, _CUBE_SIZE)
        for z in (0.0, _CUBE_SIZE)
    ]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    zs = [point[2] for point in corners]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _analytic_bbox_from_matrices(*matrices: FakeMatrix) -> tuple[float, float, float, float, float, float]:
    result = FakeMatrix()
    for matrix in reversed(matrices):
        result = matrix * result
    return _analytic_bbox(
        translation=result._translation,
        scale=result._scale,
        angle_z=result._angle_z,
    )


def _analytic_volume(*, scale: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> float:
    sx, sy, sz = scale
    return _CUBE_SIZE**3 * sx * sy * sz


def _link(
    name: str,
    *,
    target: MeasureObject,
    placement: FakePlacement | None = None,
    link_placement: FakePlacement | None = None,
    link_transform: bool = False,
    shape: object | None = None,
    scale: float | None = None,
    scale_vector: FakeVector | None = None,
    in_list: list | None = None,
    parent_group: MeasureObject | None = None,
) -> MeasureObject:
    obj = MeasureObject(
        Name=name,
        TypeId="App::Link",
        Placement=placement or FakePlacement(),
        LinkedObject=target,
        LinkTransform=link_transform,
        Shape=shape if shape is not None else NullShape(),
        InList=in_list or [],
    )
    if link_placement is not None:
        obj.LinkPlacement = link_placement
    if scale is not None:
        obj.Scale = scale
    if scale_vector is not None:
        obj.ScaleVector = scale_vector

    def _parent_geo() -> MeasureObject | None:
        return parent_group

    obj.getParentGeoFeatureGroup = _parent_geo
    return obj


@pytest.fixture(autouse=True)
def _install_freecad_doubles(monkeypatch: pytest.MonkeyPatch) -> None:
    freecad = SimpleNamespace(
        Vector=lambda x, y, z=0.0: FakeVector(x, y, z),
        Placement=FakePlacement,
        Rotation=FakeRotation,
        Matrix=FakeMatrix,
        GeoFeature=SimpleNamespace(getGlobalPlacementOf=lambda *_args, **_kwargs: None),
    )
    part = SimpleNamespace(Shape=lambda shape: shape.copy())
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)
    monkeypatch.setitem(sys.modules, "Part", part)


def _document_with(*objects: MeasureObject) -> FakeDocument:
    events: list[str] = []
    document = FakeDocument(events)
    for obj in objects:
        document.objects[obj.Name] = obj  # type: ignore[index]
    return document


def test_fake_object_without_get_global_placement_does_not_raise():
    obj = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
        Shape=UnitCubeShape(translation=(50.0, 0.0, 0.0)),
        InList=[],
    )
    obj.getParentGeoFeatureGroup = lambda: None
    shape, meta = world_shape_actions.resolve_global_shape(obj)
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(translation=(50.0, 0.0, 0.0)),
    )
    assert meta["used_linked_object"] is False


def test_healthy_link_proxy_not_double_counted():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
        shape=UnitCubeShape(translation=(50.0, 0.0, 0.0)),
        in_list=[SimpleNamespace(TypeId="App::Document")],
    )

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is False
    assert shape.BoundBox.XMin == pytest.approx(50.0)
    assert shape.BoundBox.XMax == pytest.approx(60.0)


def test_broken_link_uses_linked_object_once():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
    )

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is True
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(translation=(50.0, 0.0, 0.0)),
    )


def test_scaled_link_with_scale_vector_property():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        scale_vector=FakeVector(2.0, 2.0, 2.0),
    )

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is True
    assert_volume(shape.Volume, _analytic_volume(scale=(2.0, 2.0, 2.0)))


def test_scaled_link_with_scale_property():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link("Link", target=target, scale=3.0)

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is True
    assert_volume(shape.Volume, _analytic_volume(scale=(3.0, 3.0, 3.0)))


def test_nested_link_l2_to_l1_link_transform_false():
    box = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    box.getParentGeoFeatureGroup = lambda: None
    l1 = _link("L1", target=box)
    l1.getParentGeoFeatureGroup = lambda: None
    l2 = _link(
        "L2",
        target=l1,
        placement=FakePlacement(base=FakeVector(20.0, 0.0, 0.0)),
        link_transform=False,
    )
    l2.getParentGeoFeatureGroup = lambda: None

    shape, meta = world_shape_actions.resolve_global_shape(l2)
    assert meta["used_linked_object"] is True
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(translation=(20.0, 0.0, 0.0)),
    )


def test_nested_link_l2_to_l1_link_transform_true_uses_link_placement():
    box = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    box.getParentGeoFeatureGroup = lambda: None
    l1 = _link("L1", target=box, placement=FakePlacement(base=FakeVector(5.0, 0.0, 0.0)))
    l1.getParentGeoFeatureGroup = lambda: None
    l2 = _link(
        "L2",
        target=l1,
        placement=FakePlacement(base=FakeVector(99.0, 0.0, 0.0)),
        link_placement=FakePlacement(base=FakeVector(30.0, 0.0, 0.0)),
        link_transform=True,
    )
    l2.getParentGeoFeatureGroup = lambda: None

    shape, meta = world_shape_actions.resolve_global_shape(l2)
    assert meta["used_linked_object"] is True
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(translation=(30.0, 0.0, 0.0)),
    )


def test_cross_document_resolved_xlink_tuple():
    external = MeasureObject(
        Name="ExtBox",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    external.getParentGeoFeatureGroup = lambda: None
    link = MeasureObject(
        Name="XLink",
        TypeId="App::Link",
        Placement=FakePlacement(base=FakeVector(7.0, 0.0, 0.0)),
        LinkedObject=(external, "Box"),
        LinkTransform=False,
        Shape=NullShape(),
        InList=[],
    )
    link.getParentGeoFeatureGroup = lambda: None

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is True
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(translation=(7.0, 0.0, 0.0)),
    )


def test_cross_document_missing_target_shape_not_found():
    link = MeasureObject(
        Name="XLink",
        TypeId="App::Link",
        Placement=FakePlacement(),
        LinkedObject=(None, "Missing"),
        Shape=NullShape(),
        InList=[],
    )
    link.getParentGeoFeatureGroup = lambda: None
    with pytest.raises(TypedMutationError) as exc:
        world_shape_actions.resolve_global_shape(link)
    assert exc.value.code == "SHAPE_NOT_FOUND"


def test_rotated_app_link_matches_oracle():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(rotation=FakeRotation(angle=math.pi / 2.0)),
    )

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is True
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(angle_z=math.pi / 2.0),
    )


def test_part_feature_inside_part_applies_global_placement_once():
    part = MeasureObject(
        Name="Part",
        TypeId="App::Part",
        Placement=FakePlacement(base=FakeVector(100.0, 0.0, 0.0)),
        InList=[SimpleNamespace(TypeId="App::Document")],
    )
    part.getParentGeoFeatureGroup = lambda: None
    feature = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
        Shape=UnitCubeShape(translation=(50.0, 0.0, 0.0)),
        InList=[],
    )
    feature.getParentGeoFeatureGroup = lambda: part

    shape, meta = world_shape_actions.resolve_global_shape(feature)
    assert meta["used_linked_object"] is False
    expected = _analytic_bbox(translation=(150.0, 0.0, 0.0))
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        expected,
    )


def test_rotated_null_proxy_link_in_translated_part_matches_oracle():
    part = MeasureObject(
        Name="Part",
        TypeId="App::Part",
        Placement=FakePlacement(base=FakeVector(100.0, 0.0, 0.0)),
        InList=[SimpleNamespace(TypeId="App::Document")],
    )
    part.getParentGeoFeatureGroup = lambda: None
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: part
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(rotation=FakeRotation(angle=math.pi / 2.0)),
        parent_group=part,
    )

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is True
    expected = _analytic_bbox_from_matrices(
        FakeMatrix(translation=(100.0, 0.0, 0.0)),
        FakeMatrix(angle_z=math.pi / 2.0),
    )
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        expected,
    )


def test_nested_healthy_link_in_part_applies_parent_placement():
    part = MeasureObject(
        Name="Part",
        TypeId="App::Part",
        Placement=FakePlacement(base=FakeVector(100.0, 0.0, 0.0)),
        InList=[SimpleNamespace(TypeId="App::Document")],
    )
    part.getParentGeoFeatureGroup = lambda: None
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: part
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
        shape=UnitCubeShape(translation=(50.0, 0.0, 0.0)),
        parent_group=part,
    )

    shape, meta = world_shape_actions.resolve_global_shape(link)
    assert meta["used_linked_object"] is False
    expected = _analytic_bbox_from_matrices(
        FakeMatrix(translation=(100.0, 0.0, 0.0)),
        FakeMatrix(translation=(50.0, 0.0, 0.0)),
    )
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        expected,
    )


def test_translated_part_feature_matches_oracle():
    obj = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(base=FakeVector(5.0, -2.0, 1.0)),
        Shape=UnitCubeShape(translation=(5.0, -2.0, 1.0)),
        InList=[],
    )
    obj.getParentGeoFeatureGroup = lambda: None
    shape, _meta = world_shape_actions.resolve_global_shape(obj)
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(translation=(5.0, -2.0, 1.0)),
    )


def test_rotated_part_feature_matches_oracle():
    obj = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(rotation=FakeRotation(angle=math.pi / 2.0)),
        Shape=UnitCubeShape(angle_z=math.pi / 2.0),
        InList=[],
    )
    obj.getParentGeoFeatureGroup = lambda: None
    shape, _meta = world_shape_actions.resolve_global_shape(obj)
    assert_bbox(
        (
            shape.BoundBox.XMin,
            shape.BoundBox.YMin,
            shape.BoundBox.ZMin,
            shape.BoundBox.XMax,
            shape.BoundBox.YMax,
            shape.BoundBox.ZMax,
        ),
        _analytic_bbox(angle_z=math.pi / 2.0),
    )


def test_broken_link_target_reports_shape_not_found():
    link = MeasureObject(
        Name="Link",
        TypeId="App::Link",
        Placement=FakePlacement(),
        Shape=NullShape(),
        LinkedObject=MeasureObject(
            Name="Target",
            TypeId="Part::Feature",
            Placement=FakePlacement(),
            Shape=NullShape(),
            InList=[],
        ),
        InList=[],
    )
    link.getParentGeoFeatureGroup = lambda: None
    with pytest.raises(TypedMutationError) as exc:
        world_shape_actions.resolve_global_shape(link)
    assert exc.value.code == "SHAPE_NOT_FOUND"


def test_run_bounding_box_preserves_shape_not_found():
    events: list[str] = []
    document = _document_with(
        MeasureObject(
            Name="Link",
            TypeId="App::Link",
            Placement=FakePlacement(),
            Shape=NullShape(),
            LinkedObject=MeasureObject(
                Name="Target",
                TypeId="Part::Feature",
                Placement=FakePlacement(),
                Shape=NullShape(),
                InList=[],
            ),
            InList=[],
        )
    )
    document.objects["Link"].getParentGeoFeatureGroup = lambda: None
    collab, _api = collaborators(document, events)
    result = run_bounding_box(collab, "Doc", "Link")
    assert result["success"] is False
    assert result["error_code"] == "SHAPE_NOT_FOUND"


def test_run_measure_volume_preserves_shape_not_found():
    events: list[str] = []
    document = _document_with(
        MeasureObject(
            Name="Link",
            TypeId="App::Link",
            Placement=FakePlacement(),
            Shape=NullShape(),
            LinkedObject=MeasureObject(
                Name="Target",
                TypeId="Part::Feature",
                Placement=FakePlacement(),
                Shape=NullShape(),
                InList=[],
            ),
            InList=[],
        )
    )
    document.objects["Link"].getParentGeoFeatureGroup = lambda: None
    collab, _api = collaborators(document, events)
    result = run_measure_volume(collab, "Doc", "Link")
    assert result["success"] is False
    assert result["error_code"] == "SHAPE_NOT_FOUND"


def test_bounding_box_success_wires_used_linked_object():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
    )
    events: list[str] = []
    document = _document_with(link)
    collab, _api = collaborators(document, events)

    result = run_bounding_box(collab, "Doc", "Link")
    assert result["success"] is True
    assert result["used_linked_object"] is True
    assert result["xmin"] == pytest.approx(50.0)


def test_measure_volume_success_wires_used_linked_object_false_for_healthy_proxy():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
        shape=UnitCubeShape(translation=(50.0, 0.0, 0.0)),
    )
    events: list[str] = []
    document = _document_with(link)
    collab, _api = collaborators(document, events)

    result = run_measure_volume(collab, "Doc", "Link")
    assert result["success"] is True
    assert result["used_linked_object"] is False
    assert result["volume_mm3"] == pytest.approx(_analytic_volume())


def test_inspect_geometry_on_null_proxy_link():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
    )
    document = _document_with(link)
    payload = diagnostics_shape_actions.inspect_geometry(document, "Link")
    expected = _analytic_bbox(translation=(50.0, 0.0, 0.0))
    global_bb = payload["global_bbox"]
    assert global_bb is not None
    assert payload["local_bbox"] is None
    assert_bbox(
        (
            global_bb["xmin"],
            global_bb["ymin"],
            global_bb["zmin"],
            global_bb["xmax"],
            global_bb["ymax"],
            global_bb["zmax"],
        ),
        expected,
    )


def test_inspect_geometry_on_healthy_proxy_link():
    target = MeasureObject(
        Name="Target",
        TypeId="Part::Feature",
        Placement=FakePlacement(),
        Shape=UnitCubeShape(),
        InList=[],
    )
    target.getParentGeoFeatureGroup = lambda: None
    link = _link(
        "Link",
        target=target,
        placement=FakePlacement(base=FakeVector(50.0, 0.0, 0.0)),
        shape=UnitCubeShape(translation=(50.0, 0.0, 0.0)),
    )
    document = _document_with(link)
    payload = diagnostics_shape_actions.inspect_geometry(document, "Link")
    expected = _analytic_bbox(translation=(50.0, 0.0, 0.0))
    global_bb = payload["global_bbox"]
    assert global_bb is not None
    assert_bbox(
        (
            global_bb["xmin"],
            global_bb["ymin"],
            global_bb["zmin"],
            global_bb["xmax"],
            global_bb["ymax"],
            global_bb["zmax"],
        ),
        expected,
    )


def test_inspect_geometry_global_bbox_matches_independent_oracle():
    obj = MeasureObject(
        Name="Box",
        TypeId="Part::Feature",
        Placement=FakePlacement(base=FakeVector(12.0, 3.0, -4.0)),
        Shape=UnitCubeShape(translation=(12.0, 3.0, -4.0)),
        InList=[],
    )
    obj.getParentGeoFeatureGroup = lambda: None
    document = _document_with(obj)
    payload = diagnostics_shape_actions.inspect_geometry(document, "Box")
    expected = _analytic_bbox(translation=(12.0, 3.0, -4.0))
    global_bb = payload["global_bbox"]
    assert global_bb is not None
    assert_bbox(
        (
            global_bb["xmin"],
            global_bb["ymin"],
            global_bb["zmin"],
            global_bb["xmax"],
            global_bb["ymax"],
            global_bb["zmax"],
        ),
        expected,
    )


def test_world_shape_module_is_shared():
    world_shape_source = (
        Path(__file__).resolve().parents[2]
        / "addon"
        / "FreeCADMCP"
        / "rpc_server"
        / "methods"
        / "cad_methods_ops"
        / "world_shape_actions.py"
    ).read_text(encoding="utf-8")
    assert_code_contains(
        world_shape_source,
        "resolve_global_shape",
        "ScaleVector",
        "getParentGeoFeatureGroup",
        "used_linked_object",
    )
    assert "getTransform" not in world_shape_source
