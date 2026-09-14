"""Apply helpers for typed gear mutations. Apply never recomputes the document."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .typed_runtime import (
    TypedMutationError,
    load_module,
    module_callable,
    object_name,
    require_object,
)


@dataclass(frozen=True, slots=True)
class GearReceipt:
    body: str
    sketch: str
    feature: str
    teeth: int
    module: float
    pitch_dia: float
    tooth_profile: str


def _freecad() -> object:
    return load_module("FreeCAD")


def _part() -> object:
    return load_module("Part")


def _sketcher() -> object:
    return load_module("Sketcher")


def _vector(x: float, y: float, z: float = 0.0) -> object:
    return module_callable(_freecad(), "Vector")(x, y, z)


def _set_bool(feature: object, name: str, value: bool) -> None:
    names = getattr(feature, "PropertiesList", None)
    if isinstance(names, (list, tuple)) and name not in names and not hasattr(feature, name):
        return
    if hasattr(feature, name):
        setattr(feature, name, value)


def _set_extrusion_one_side(feature: object) -> None:
    names_obj = getattr(feature, "PropertiesList", ())
    names = set(names_obj) if isinstance(names_obj, (list, tuple)) else set()
    if "SideType" in names or hasattr(feature, "SideType"):
        try:
            setattr(feature, "SideType", "One side")
            return
        except Exception:
            pass
    if "Symmetric" in names or hasattr(feature, "Symmetric"):
        setattr(feature, "Symmetric", False)
        return
    if "Midplane" in names or hasattr(feature, "Midplane"):
        setattr(feature, "Midplane", False)


def _attach_xy(body: object, sketch: object) -> None:
    origin = getattr(body, "Origin", None)
    plane = None
    variants = {"XY_Plane", "XY-plane", "XY-Plane"}
    for feature in getattr(origin, "OriginFeatures", []) or []:
        role = str(getattr(feature, "Role", ""))
        label = str(getattr(feature, "Label", ""))
        name = str(getattr(feature, "Name", ""))
        if role in variants or label in variants or name in variants:
            plane = feature
            break
    if plane is None:
        return
    setattr(sketch, "AttachmentSupport", [(plane, "")])
    setattr(sketch, "MapMode", "FlatFace")


def _ensure_body(document: object, body_name: str | None, gear_name: str) -> object:
    if body_name:
        return require_object(document, body_name, code="BODY_NOT_FOUND")
    adder = getattr(document, "addObject", None)
    if not callable(adder):
        raise TypedMutationError("INVALID_DOCUMENT", "document must provide addObject")
    return adder("PartDesign::Body", gear_name + "_Body")


def _new_sketch(body: object, sketch_name: str) -> object:
    factory = getattr(body, "newObject", None)
    if not callable(factory):
        raise TypedMutationError("INVALID_BODY", "Body must provide newObject")
    sketch = factory("Sketcher::SketchObject", sketch_name)
    _attach_xy(body, sketch)
    return sketch


def _add_point(
    points: list[object],
    x: float,
    y: float,
    *,
    min_length: float,
) -> None:
    point = _vector(x, y, 0.0)
    if points:
        delta = points[-1] - point  # type: ignore[operator]
        if float(getattr(delta, "Length", 0.0)) <= min_length:
            return
    points.append(point)


def _close_points(points: list[object], min_length: float) -> None:
    if len(points) < 2:
        raise TypedMutationError("INVALID_PROFILE", "gear profile did not produce geometry")
    delta = points[0] - points[-1]  # type: ignore[operator]
    if float(getattr(delta, "Length", 0.0)) > min_length:
        points.append(points[0])


def _profile_to_sketch(sketch: object, points: list[object], min_length: float) -> int:
    part = _part()
    add_geometry = getattr(sketch, "addGeometry", None)
    if not callable(add_geometry):
        raise TypedMutationError("INVALID_SKETCH", "sketch must provide addGeometry")
    if len(points) >= 4:
        bspline_cls = getattr(part, "BSplineCurve", None)
        if bspline_cls is not None:
            try:
                curve = bspline_cls()
                interpolate = getattr(curve, "interpolate", None)
                to_shape = getattr(curve, "toShape", None)
                if callable(interpolate):
                    interpolate(Points=points, PeriodicFlag=True)
                    add_geometry(curve, False)
                    return 1
            except Exception:
                pass
    sketcher = _sketcher()
    line_segment = module_callable(part, "LineSegment")
    constraint = module_callable(sketcher, "Constraint")
    add_constraint = getattr(sketch, "addConstraint", None)
    if not callable(add_constraint):
        raise TypedMutationError("INVALID_SKETCH", "sketch must provide addConstraint")
    indices: list[object] = []
    for idx in range(len(points) - 1):
        p1 = points[idx]
        p2 = points[idx + 1]
        delta = p2 - p1  # type: ignore[operator]
        if float(getattr(delta, "Length", 0.0)) <= min_length:
            continue
        geo = add_geometry(line_segment(p1, p2), False)
        indices.append(geo)
        if len(indices) > 1:
            add_constraint(constraint("Coincident", indices[-2], 2, indices[-1], 1))
    if len(indices) > 1:
        add_constraint(constraint("Coincident", indices[-1], 2, indices[0], 1))
    return len(indices)


def _construction_circles(
    sketch: object,
    radii: tuple[tuple[str, float], ...],
) -> None:
    part = _part()
    sketcher = _sketcher()
    circle = module_callable(part, "Circle")
    constraint = module_callable(sketcher, "Constraint")
    add_geometry = getattr(sketch, "addGeometry", None)
    add_constraint = getattr(sketch, "addConstraint", None)
    if not callable(add_geometry) or not callable(add_constraint):
        return
    z_axis = _vector(0.0, 0.0, 1.0)
    origin = _vector(0.0, 0.0, 0.0)
    for _label, radius in radii:
        idx = add_geometry(circle(origin, z_axis, radius), True)
        try:
            add_constraint(constraint("Radius", idx, radius))
            add_constraint(constraint("Coincident", idx, 3, -1, 1))
        except Exception:
            continue


def _maybe_bore(sketch: object, bore_diameter: float) -> None:
    if bore_diameter <= 0:
        return
    part = _part()
    sketcher = _sketcher()
    circle = module_callable(part, "Circle")
    constraint = module_callable(sketcher, "Constraint")
    add_geometry = getattr(sketch, "addGeometry", None)
    add_constraint = getattr(sketch, "addConstraint", None)
    if not callable(add_geometry):
        return
    idx = add_geometry(
        circle(_vector(0.0, 0.0, 0.0), _vector(0.0, 0.0, 1.0), bore_diameter / 2.0),
        False,
    )
    if callable(add_constraint):
        try:
            add_constraint(constraint("Radius", idx, bore_diameter / 2.0))
            add_constraint(constraint("Coincident", idx, 3, -1, 1))
        except Exception:
            return


def _validate_gear_dims(
    *,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float,
    bore_diameter: float,
    clearance: float,
    backlash: float,
) -> tuple[float, float, float, float, float]:
    if teeth < 3:
        raise TypedMutationError("INVALID_ARGUMENT", "teeth must be >= 3")
    if module <= 0:
        raise TypedMutationError("INVALID_ARGUMENT", "module must be > 0")
    if width <= 0:
        raise TypedMutationError("INVALID_ARGUMENT", "width must be > 0")
    angle = math.radians(pressure_angle)
    if not 0 < angle < math.radians(45):
        raise TypedMutationError("INVALID_ARGUMENT", "pressure_angle must be 1-44 degrees")
    if bore_diameter < 0 or clearance < 0 or backlash < 0:
        raise TypedMutationError("INVALID_ARGUMENT", "clearance, backlash, and bore_diameter must be >= 0")
    pitch = module * teeth / 2.0
    base = pitch * math.cos(angle)
    outer = pitch + module
    root = max(pitch - (1.25 * module + clearance), module * 0.05)
    if bore_diameter and bore_diameter >= 2.0 * root:
        raise TypedMutationError("INVALID_ARGUMENT", "bore_diameter must be smaller than root diameter")
    return angle, pitch, base, outer, root


def _involute_points(
    *,
    teeth: int,
    pitch: float,
    base: float,
    outer: float,
    root: float,
    pressure_angle: float,
    backlash: float,
    samples: int,
    min_length: float,
) -> list[object]:
    if outer <= base:
        raise TypedMutationError(
            "INVALID_ARGUMENT",
            "Addendum circle must be larger than the base circle",
        )
    inv_alpha = math.tan(pressure_angle) - pressure_angle
    delta = math.pi / (2.0 * teeth) - backlash / (2.0 * pitch)
    t_tip = math.sqrt((outer / base) ** 2 - 1.0)
    has_undercut = root < base
    t_root = 0.0 if has_undercut else math.sqrt((root / base) ** 2 - 1.0)
    points: list[object] = []

    def ix(t: float) -> float:
        return base * (math.cos(t) + t * math.sin(t))

    def iy(t: float) -> float:
        return base * (math.sin(t) - t * math.cos(t))

    def polar(t: float) -> float:
        return t - math.atan(t)

    def rot(x: float, y: float, a: float) -> tuple[float, float]:
        return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)

    for tooth in range(teeth):
        theta = 2.0 * math.pi * tooth / teeth
        phi_r = theta - delta - inv_alpha
        phi_l = theta + delta + inv_alpha
        if has_undercut:
            _add_point(points, root * math.cos(phi_r), root * math.sin(phi_r), min_length=min_length)
        for sample in range(samples + 1):
            t = t_root + (t_tip - t_root) * sample / samples
            x, y = rot(ix(t), iy(t), phi_r)
            _add_point(points, x, y, min_length=min_length)
        r_tip = phi_r + polar(t_tip)
        l_tip = phi_l - polar(t_tip)
        tip_steps = max(2, samples // 4)
        for step in range(1, tip_steps):
            a = r_tip + (l_tip - r_tip) * step / tip_steps
            _add_point(points, outer * math.cos(a), outer * math.sin(a), min_length=min_length)
        for sample in range(samples, -1, -1):
            t = t_root + (t_tip - t_root) * sample / samples
            x, y = rot(ix(t), -iy(t), phi_l)
            _add_point(points, x, y, min_length=min_length)
        if has_undercut:
            _add_point(points, root * math.cos(phi_l), root * math.sin(phi_l), min_length=min_length)
            arc_start = phi_l
            arc_end = (theta + 2.0 * math.pi / teeth) - delta - inv_alpha
        else:
            arc_start = phi_l - polar(t_root)
            arc_end = (theta + 2.0 * math.pi / teeth) - delta - inv_alpha + polar(t_root)
        root_steps = max(2, samples // 2)
        for step in range(1, root_steps + 1):
            a = arc_start + (arc_end - arc_start) * step / root_steps
            _add_point(points, root * math.cos(a), root * math.sin(a), min_length=min_length)
    return points


def _add_arc(
    points: list[object],
    radius: float,
    start: float,
    end: float,
    steps: int,
    min_length: float,
) -> None:
    count = max(1, int(steps))
    for idx in range(1, count + 1):
        a = start + (end - start) * idx / count
        _add_point(points, radius * math.cos(a), radius * math.sin(a), min_length=min_length)


def _spur_profile_points(
    *,
    profile: str,
    teeth: int,
    pitch: float,
    base: float,
    outer: float,
    root: float,
    pressure_angle: float,
    backlash: float,
    samples: int,
    module: float,
    min_length: float,
) -> list[object]:
    if profile == "involute":
        return _involute_points(
            teeth=teeth,
            pitch=pitch,
            base=base,
            outer=outer,
            root=root,
            pressure_angle=pressure_angle,
            backlash=backlash,
            samples=samples,
            min_length=min_length,
        )
    points: list[object] = []
    tooth_angle = 2.0 * math.pi / teeth
    if profile == "trapezoid":
        for tooth in range(teeth):
            theta = 2.0 * math.pi * tooth / teeth
            _add_point(points, root * math.cos(theta - tooth_angle * 0.32), root * math.sin(theta - tooth_angle * 0.32), min_length=min_length)
            _add_point(points, outer * math.cos(theta - tooth_angle * 0.16), outer * math.sin(theta - tooth_angle * 0.16), min_length=min_length)
            _add_point(points, outer * math.cos(theta + tooth_angle * 0.16), outer * math.sin(theta + tooth_angle * 0.16), min_length=min_length)
            _add_point(points, root * math.cos(theta + tooth_angle * 0.32), root * math.sin(theta + tooth_angle * 0.32), min_length=min_length)
            _add_arc(points, root, theta + tooth_angle * 0.32, theta + tooth_angle * 0.68, max(1, samples // 3), min_length)
    elif profile == "straight":
        for tooth in range(teeth):
            theta = 2.0 * math.pi * tooth / teeth
            _add_point(points, root * math.cos(theta - tooth_angle * 0.25), root * math.sin(theta - tooth_angle * 0.25), min_length=min_length)
            _add_point(points, outer * math.cos(theta - tooth_angle * 0.25), outer * math.sin(theta - tooth_angle * 0.25), min_length=min_length)
            _add_point(points, outer * math.cos(theta + tooth_angle * 0.25), outer * math.sin(theta + tooth_angle * 0.25), min_length=min_length)
            _add_point(points, root * math.cos(theta + tooth_angle * 0.25), root * math.sin(theta + tooth_angle * 0.25), min_length=min_length)
            _add_arc(points, root, theta + tooth_angle * 0.25, theta + tooth_angle * 0.75, max(1, samples // 3), min_length)
    elif profile == "cycloidal":
        steps = max(8, min(samples * 2, 12))
        for tooth in range(teeth):
            theta = 2.0 * math.pi * tooth / teeth
            for sample in range(steps):
                local = -tooth_angle / 2.0 + tooth_angle * sample / float(steps)
                x = min(1.0, abs(local) / (tooth_angle / 2.0))
                shape = 0.5 + 0.5 * math.cos(math.pi * x)
                radius = root + (outer - root) * shape
                _add_point(points, radius * math.cos(theta + local), radius * math.sin(theta + local), min_length=min_length)
    elif profile == "circular_arc":
        for tooth in range(teeth):
            theta = 2.0 * math.pi * tooth / teeth
            _add_arc(points, outer, theta - tooth_angle * 0.25, theta + tooth_angle * 0.25, max(6, samples), min_length)
            _add_arc(points, root, theta + tooth_angle * 0.25, theta + tooth_angle * 0.75, max(2, samples // 2), min_length)
    else:
        hub = max(pitch - 0.75 * module, module * 0.4)
        pin = max(min(module * 0.55, hub * math.sin(tooth_angle * 0.34)), module * 0.18)
        steps = max(8, min(samples * 3, 16))
        for tooth in range(teeth):
            theta = 2.0 * math.pi * tooth / teeth
            for sample in range(steps):
                local = -tooth_angle / 2.0 + tooth_angle * sample / float(steps)
                radius = hub + pin * max(0.0, math.cos(local))
                _add_point(points, radius * math.cos(theta + local), radius * math.sin(theta + local), min_length=min_length)
    return points


def _normalize_profile(tooth_profile: str) -> str:
    aliases = {
        "straight_teeth": "straight",
        "square": "straight",
        "spline": "straight",
        "trapezoid_straight_teeth": "trapezoid",
        "novikov": "circular_arc",
        "circular": "circular_arc",
        "arc": "circular_arc",
        "lantern": "pin",
        "pin_gear": "pin",
    }
    profile = tooth_profile.strip().lower().replace("-", "_").replace(" ", "_")
    profile = aliases.get(profile, profile)
    valid = {"involute", "cycloidal", "trapezoid", "straight", "circular_arc", "pin"}
    if profile not in valid:
        raise TypedMutationError(
            "INVALID_ARGUMENT",
            "tooth_profile must be one of: " + ", ".join(sorted(valid)),
        )
    return profile


def _finish_sketch(
    sketch: object,
    points: list[object],
    *,
    bore_diameter: float,
    min_length: float,
) -> None:
    _close_points(points, min_length)
    _profile_to_sketch(sketch, points, min_length)
    _maybe_bore(sketch, bore_diameter)


def create_involute_gear(
    document: object,
    *,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float,
    bore_diameter: float,
    clearance: float,
    backlash: float,
    samples_per_flank: int,
    body_name: str | None,
    sketch_name: str | None,
) -> dict[str, object]:
    angle, pitch, base, outer, root = _validate_gear_dims(
        teeth=teeth,
        module=module,
        width=width,
        pressure_angle=pressure_angle,
        bore_diameter=bore_diameter,
        clearance=clearance,
        backlash=backlash,
    )
    samples = max(2, min(samples_per_flank, 2))
    body = _ensure_body(document, body_name, gear_name)
    sketch = _new_sketch(body, sketch_name or (gear_name + "_Sketch"))
    points = _involute_points(
        teeth=teeth,
        pitch=pitch,
        base=base,
        outer=outer,
        root=root,
        pressure_angle=angle,
        backlash=backlash,
        samples=samples,
        min_length=1e-8,
    )
    _finish_sketch(
        sketch,
        points,
        bore_diameter=bore_diameter,
        min_length=1e-8,
    )
    factory = getattr(body, "newObject", None)
    if not callable(factory):
        raise TypedMutationError("INVALID_BODY", "Body must provide newObject")
    pad = factory("PartDesign::Pad", gear_name)
    setattr(pad, "Profile", (sketch, [""]))
    setattr(pad, "Length", width)
    _set_extrusion_one_side(pad)
    return {
        "body": object_name(body),
        "sketch": object_name(sketch),
        "feature": object_name(pad),
        "teeth": teeth,
        "module": module,
        "pitch_dia": 2.0 * pitch,
        "tooth_profile": "involute",
    }


def _helical_profile_to_sketch(
    sketch: object,
    *,
    pitch_radius: float,
    module: float,
    bore_diameter: float,
) -> None:
    part = _part()
    add_geometry = getattr(sketch, "addGeometry", None)
    if not callable(add_geometry):
        raise TypedMutationError("INVALID_SKETCH", "sketch must provide addGeometry")
    circle = module_callable(part, "Circle")
    add_geometry(
        circle(_vector(pitch_radius, 0.0, 0.0), _vector(0.0, 0.0, 1.0), module),
        False,
    )
    _maybe_bore(sketch, bore_diameter)


def create_helical_gear(
    document: object,
    *,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    helix_angle: float,
    pressure_angle: float,
    bore_diameter: float,
    clearance: float,
    backlash: float,
    samples_per_flank: int,
    body_name: str | None,
) -> dict[str, object]:
    angle, pitch, base, outer, root = _validate_gear_dims(
        teeth=teeth,
        module=module,
        width=width,
        pressure_angle=pressure_angle,
        bore_diameter=bore_diameter,
        clearance=clearance,
        backlash=backlash,
    )
    del angle, base, outer, root, samples_per_flank
    body = _ensure_body(document, body_name, gear_name)
    sketch = _new_sketch(body, gear_name + "_Sketch")
    _helical_profile_to_sketch(
        sketch,
        pitch_radius=pitch,
        module=module,
        bore_diameter=bore_diameter,
    )
    helix = math.radians(helix_angle)
    pitch_len = width / math.tan(helix) if abs(math.tan(helix)) > 1e-9 else 1e6
    factory = getattr(body, "newObject", None)
    if not callable(factory):
        raise TypedMutationError("INVALID_BODY", "Body must provide newObject")
    feature = factory("PartDesign::AdditiveHelix", gear_name)
    setattr(feature, "Profile", sketch)
    setattr(feature, "ReferenceAxis", (sketch, ["V_Axis"]))
    setattr(feature, "Mode", 0)
    setattr(feature, "Pitch", pitch_len)
    setattr(feature, "Height", width)
    setattr(feature, "Angle", 0)
    setattr(feature, "Growth", 0)
    tip_setter = getattr(body, "Tip", None)
    if tip_setter is not None:
        setattr(body, "Tip", feature)
    return {
        "body": object_name(body),
        "sketch": object_name(sketch),
        "feature": object_name(feature),
        "teeth": teeth,
        "module": module,
        "pitch_dia": 2.0 * pitch,
        "tooth_profile": "helical",
    }


def create_spur_gear(
    document: object,
    *,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float,
    bore_diameter: float,
    clearance: float,
    backlash: float,
    samples_per_flank: int,
    body_name: str | None,
    sketch_name: str | None,
    tooth_profile: str,
) -> dict[str, object]:
    profile = _normalize_profile(tooth_profile)
    angle, pitch, base, outer, root = _validate_gear_dims(
        teeth=teeth,
        module=module,
        width=width,
        pressure_angle=pressure_angle,
        bore_diameter=bore_diameter,
        clearance=clearance,
        backlash=backlash,
    )
    if root >= outer:
        raise TypedMutationError("INVALID_ARGUMENT", "root radius must be smaller than outer radius")
    if _normalize_profile(tooth_profile) == "involute":
        return create_involute_gear(
            document,
            gear_name=gear_name,
            teeth=teeth,
            module=module,
            width=width,
            pressure_angle=pressure_angle,
            bore_diameter=bore_diameter,
            clearance=clearance,
            backlash=backlash,
            samples_per_flank=samples_per_flank,
            body_name=body_name,
            sketch_name=sketch_name,
        )
    samples = max(2, min(samples_per_flank, 2))
    body = _ensure_body(document, body_name, gear_name)
    sketch = _new_sketch(body, sketch_name or (gear_name + "_Sketch"))
    points = _spur_profile_points(
        profile=profile,
        teeth=teeth,
        pitch=pitch,
        base=base,
        outer=outer,
        root=root,
        pressure_angle=angle,
        backlash=backlash,
        samples=samples,
        module=module,
        min_length=1e-7,
    )
    _finish_sketch(
        sketch,
        points,
        bore_diameter=bore_diameter,
        min_length=1e-7,
    )
    factory = getattr(body, "newObject", None)
    if not callable(factory):
        raise TypedMutationError("INVALID_BODY", "Body must provide newObject")
    pad = factory("PartDesign::Pad", gear_name)
    setattr(pad, "Profile", (sketch, [""]))
    setattr(pad, "Length", width)
    _set_extrusion_one_side(pad)
    _set_bool(pad, "Reversed", False)
    return {
        "body": object_name(body),
        "sketch": object_name(sketch),
        "feature": object_name(pad),
        "teeth": teeth,
        "module": module,
        "pitch_dia": 2.0 * pitch,
        "tooth_profile": profile,
    }


__all__ = [
    "create_helical_gear",
    "create_involute_gear",
    "create_spur_gear",
]
