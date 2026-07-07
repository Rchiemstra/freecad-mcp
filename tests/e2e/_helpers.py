"""Shared helpers for the live FreeCAD e2e / core-repro tests.

These helpers use FreeCAD lazily (inside functions) so that simply importing
this module does not require FreeCAD to be present. The accompanying test
modules gate collection with ``pytest.importorskip`` at the top.
"""
from __future__ import annotations

import math
from typing import Optional


def _fc():
    import FreeCAD  # type: ignore
    return FreeCAD


def _part():
    import Part  # type: ignore
    return Part


def origin_plane(body, label: str):
    """Return the named base plane (``'XY_Plane'``/``'XZ_Plane'``/``'YZ_Plane'``)
    of a PartDesign Body's Origin, or raise."""
    origin = body.Origin
    for feat in getattr(origin, "OriginFeatures", []) or []:
        if feat.Label == label or feat.Name == label:
            return feat
    # Fall back to dynamic property access (Origin exposes XY_Plane etc.).
    cand = getattr(origin, label, None)
    if cand is not None:
        return cand
    raise LookupError(f"Origin plane {label!r} not found on body {body.Label!r}")


def add_xy_sketch(body, name: str = "Sketch", plane_label: str = "XY_Plane"):
    """Create a sketch in *body* attached to one of the body's origin planes."""
    FreeCAD = _fc()
    plane = origin_plane(body, plane_label)
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(plane, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = FreeCAD.Placement()
    return sk


def make_padded_circle(body, radius=2.0, length=1.0, plane_label="XY_Plane",
                       sketch_name="CircleSketch", pad_name="CirclePad"):
    """Body identity: sketch a circle on *plane_label*, pad it, return (sketch, pad)."""
    FreeCAD = _fc()
    Part = _part()
    sk = add_xy_sketch(body, sketch_name, plane_label)
    sk.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), radius), False)
    FreeCAD.ActiveDocument.recompute()
    pad = body.newObject("PartDesign::Pad", pad_name)
    pad.Profile = sk
    pad.Length = length
    FreeCAD.ActiveDocument.recompute()
    return sk, pad


def face_global_normal(obj, face_name: str):
    """Global normal of a face of *obj* (face_name like ``'Face3'``)."""
    FreeCAD = _fc()
    idx = int(face_name[4:]) - 1
    face = obj.Shape.Faces[idx]
    local_axis = face.Surface.Axis
    gp = obj.getGlobalPlacement()
    return gp.Rotation * FreeCAD.Vector(local_axis.x, local_axis.y, local_axis.z)


def face_global_center(obj, face_name: str):
    """Global center-of-mass of a face of *obj*."""
    FreeCAD = _fc()
    idx = int(face_name[4:]) - 1
    face = obj.Shape.Faces[idx]
    return obj.getGlobalPlacement() * face.CenterOfMass


def find_face(obj, *, normal=None, center=None, radius=None, kind=None,
              tol=1e-3) -> Optional[str]:
    """Find the first face of *obj* matching the given geometric criteria.

    Returns the ``'FaceN'`` name or ``None``. Filters:
      * ``kind``     - surface type id, e.g. ``'Plane'`` or ``'Cylinder'``.
      * ``normal``   - (x,y,z) the face global normal must be parallel to.
      * ``center``   - (x,y,z) the face global center must be within *tol* of.
      * ``radius``   - cylinder face radius match within *tol*.
    """
    FreeCAD = _fc()
    gp = obj.getGlobalPlacement()
    for i, face in enumerate(obj.Shape.Faces, start=1):
        surf = face.Surface
        sname = type(surf).__name__
        if kind and sname != kind:
            continue
        if normal is not None:
            ax = gp.Rotation * FreeCAD.Vector(surf.Axis.x, surf.Axis.y, surf.Axis.z)
            if abs(ax.dot(FreeCAD.Vector(*normal)) - 1.0) > tol:
                continue
        if radius is not None and hasattr(surf, "Radius"):
            if abs(surf.Radius - radius) > tol:
                continue
        if center is not None:
            c = gp * face.CenterOfMass
            if (c - FreeCAD.Vector(*center)).Length > tol:
                continue
        return f"Face{i}"
    return None


def plane_global_normal(datum):
    """Global normal of a PartDesign::Plane datum (its Z axis in world space)."""
    FreeCAD = _fc()
    gp = datum.getGlobalPlacement()
    return gp.Rotation * FreeCAD.Vector(0, 0, 1)


def plane_global_base(datum):
    """Global base point of a PartDesign::Plane datum."""
    return datum.getGlobalPlacement().Base


def distance_point_to_plane(point, plane_base, plane_normal) -> float:
    """Signed distance from *point* to an infinite plane."""
    FreeCAD = _fc()
    d = point - plane_base
    return float(d.dot(FreeCAD.Vector(*plane_normal)) if not hasattr(plane_normal, "dot") else d.dot(plane_normal))


def assert_vec_eq(a, b, tol=1e-3) -> None:
    ax, ay, az = (a.x, a.y, a.z)
    bx, by, bz = (b.x, b.y, b.z)
    err = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
    assert err <= tol, f"Vector mismatch: ({ax},{ay},{az}) vs ({bx},{by},{bz}) err={err:.4e}"


def assert_parallel(a, b, tol=1e-3) -> None:
    dot = a.x * b.x + a.y * b.y + a.z * b.z
    sin2 = max(0.0, 1.0 - dot * dot)
    assert sin2 <= tol * tol, (
        f"Not parallel: ({a.x},{a.y},{a.z}) vs ({b.x},{b.y},{b.z}) |sin|={math.sqrt(sin2):.4e}"
    )
