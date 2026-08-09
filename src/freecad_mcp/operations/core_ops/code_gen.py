from __future__ import annotations

from ...template_resources import read_template_lines, render_template_lines, render_template_text


def _build_assertion_code(
    feature_name: str,
    sketch_name: str,
    check_direction: bool = True,
) -> list[str]:
    """I2 — render the silent-build assertion snippet for a PartDesign feature.

    Appended to a pad/pocket/loft/sweep op's generated code so a wrong-direction
    or misplaced build (P2/P3) is surfaced as a clear failure instead of being
    silently marked Up-to-date.
    """
    return render_template_lines(
        "diagnostics/build_assertion.py.txt",
        feature_name=repr(feature_name),
        feature_name_repr=repr(feature_name),
        sketch_name=repr(sketch_name),
        check_direction=repr(check_direction),
    )

def _indented_build_assertion(feature_name: str, sketch_name: str) -> str:
    """Render the I2 build assertion pre-indented by 4 spaces.

    The pad/pocket templates inject this via a ``$verification`` placeholder that
    sits inside the feature-build ``try`` block, so the assertion runs *inside*
    the transaction (a failed direction/shape check aborts and leaves no partial
    feature). ``string.Template`` does not auto-indent multi-line substitutions,
    so every line is prefixed here; the placeholder itself is at column 0.
    """
    return "\n".join(
        "    " + line
        for line in _build_assertion_code(feature_name, sketch_name, check_direction=True)
    )

def _geom_line(code: str, geom: dict) -> str:
    """Return a Python expression that adds one geometry element to _sk."""
    t = geom.get("type", "").lower()
    c = repr(bool(geom.get("construction")))
    if t == "line":
        s, e = geom["start"], geom["end"]
        return render_template_text(
            "core/geom_line.py.txt",
            x1=repr(s["x"]),
            y1=repr(s["y"]),
            x2=repr(e["x"]),
            y2=repr(e["y"]),
            construction=c,
        ).strip()
    if t == "circle":
        ct = geom.get("center", {"x": 0, "y": 0})
        r = geom.get("radius", 1)
        return render_template_text(
            "core/geom_circle.py.txt",
            cx=repr(ct["x"]),
            cy=repr(ct["y"]),
            radius=repr(r),
            construction=c,
        ).strip()
    if t == "arc":
        ct = geom.get("center", {"x": 0, "y": 0})
        r = geom.get("radius", 1)
        sa = geom.get("start_angle", 0)
        ea = geom.get("end_angle", 90)
        return render_template_text(
            "core/geom_arc.py.txt",
            cx=repr(ct["x"]),
            cy=repr(ct["y"]),
            radius=repr(r),
            start_angle=repr(sa),
            end_angle=repr(ea),
            construction=c,
        ).strip()
    if t == "rectangle":
        x1, y1, x2, y2 = (
            geom.get("x1", 0),
            geom.get("y1", 0),
            geom.get("x2", 10),
            geom.get("y2", 10),
        )
        return render_template_text(
            "core/geom_rectangle.py.txt",
            x1=repr(x1),
            y1=repr(y1),
            x2=repr(x2),
            y2=repr(y2),
            construction=c,
        ).strip()
    if t == "point":
        x, y = geom.get("x", 0), geom.get("y", 0)
        return render_template_text(
            "core/geom_point.py.txt",
            x=repr(x),
            y=repr(y),
            construction=c,
        ).strip()
    return f"raise ValueError('Unknown geometry type: {t!r}')"

def _constraint_stmt(args: str, name: str | None = None) -> str:
    if name:
        return render_template_text(
            "parametric/constraint_named.py.txt",
            args=args,
            constraint_name=repr(name),
        ).strip()
    return render_template_text("core/constraint.py.txt", args=args).strip()

def _distance_constraint_args(c: dict) -> str:
    if "geo2" in c:
        return (
            f"'Distance',{c['geo1']},{c.get('pos1',0)},"
            f"{c['geo2']},{c.get('pos2',0)},{c['value']}"
        )
    if "pos" in c:
        return f"'Distance',{c['geo']},{c['pos']},{c['value']}"
    return f"'Distance',{c['geo']},{c['value']}"


def _axis_distance_constraint_args(c: dict, axis: str) -> str:
    if "pos" in c:
        return f"'{axis}',{c['geo']},{c['pos']},{c['value']}"
    return f"'{axis}',{c['geo']},{c['value']}"


def _angle_constraint_args(c: dict) -> str:
    if "geo2" in c:
        return (
            f"'Angle',{c['geo1']},{c.get('pos1',0)},"
            f"{c['geo2']},{c.get('pos2',0)},{c['value']}"
        )
    return f"'Angle',{c['geo']},{c['value']}"


def _constraint_args(c: dict) -> str | None:
    t = c.get("type", "")
    if t == "Coincident":
        return f"'Coincident',{c['geo1']},{c['pos1']},{c['geo2']},{c['pos2']}"
    if t in ("Horizontal", "Vertical", "Radius", "Diameter", "Block"):
        key = "geo"
        return f"'{t}',{c[key]}" + (f",{c['value']}" if t in ("Radius", "Diameter") else "")
    if t == "Distance":
        return _distance_constraint_args(c)
    if t == "DistanceX":
        return _axis_distance_constraint_args(c, "DistanceX")
    if t == "DistanceY":
        return _axis_distance_constraint_args(c, "DistanceY")
    if t == "Angle":
        return _angle_constraint_args(c)
    if t in ("Parallel", "Perpendicular", "Equal", "Tangent"):
        return f"{t!r},{c['geo1']},{c['geo2']}"
    if t == "PointOnObject":
        return f"'PointOnObject',{c['geo1']},{c['pos1']},{c['geo2']}"
    if t == "Symmetric":
        return (
            f"'Symmetric',{c['geo1']},{c['pos1']},{c['geo2']},"
            f"{c['pos2']},{c['geo3']},{c.get('pos3',0)}"
        )
    return None


def _constraint_line(c: dict) -> str:
    """Return a Python expression that adds one Sketcher constraint to _sk."""
    t = c.get("type", "")
    args = _constraint_args(c)
    if args is None:
        return f"raise ValueError('Unknown constraint type: {t!r}')"
    return _constraint_stmt(args, c.get("name"))

def _partdesign_bool_property_helper_code() -> list[str]:
    return read_template_lines("core/partdesign_bool_property_helper.py.txt")

def _partdesign_extrusion_helper_code() -> list[str]:
    return read_template_lines("core/partdesign_extrusion_helper.py.txt")

def _partdesign_pattern_helper_code() -> list[str]:
    return read_template_lines("core/partdesign_pattern_helper.py.txt")
