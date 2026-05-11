"""
Layer-B geometric assertion helpers.

These helpers work in pure Python (no FreeCAD import needed).
They are designed to be used in mock-based unit tests that verify the
*generated code* contains correct geometric operations, and in integration
tests that execute code inside a live FreeCAD instance.
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Tolerance defaults (overridable per call)
# ---------------------------------------------------------------------------

_DEFAULT_LENGTH_TOL = 1e-4   # mm
_DEFAULT_ANGLE_TOL  = 1e-5   # rad
_DEFAULT_VOL_REL    = 1e-6   # relative


# ---------------------------------------------------------------------------
# Pure-Python geometric helpers (for analytic checks)
# ---------------------------------------------------------------------------

def assert_volume(actual: float, expected: float, *, rel_tol: float = _DEFAULT_VOL_REL) -> None:
    """Assert that *actual* volume is within *rel_tol* of *expected*."""
    if expected == 0:
        assert abs(actual) < _DEFAULT_LENGTH_TOL ** 3, f"Volume {actual!r} should be 0"
        return
    err = abs(actual - expected) / abs(expected)
    assert err <= rel_tol, (
        f"Volume mismatch: got {actual:.6g} expected {expected:.6g} "
        f"(rel error {err:.2e} > tol {rel_tol:.2e})"
    )


def assert_bbox(
    actual: tuple[float, float, float, float, float, float],
    expected: tuple[float, float, float, float, float, float],
    *,
    tol: float = _DEFAULT_LENGTH_TOL,
) -> None:
    """Assert bounding-box components match within *tol*.

    Both *actual* and *expected* are ``(xmin, ymin, zmin, xmax, ymax, zmax)``.
    """
    for i, (a, e) in enumerate(zip(actual, expected)):
        assert abs(a - e) <= tol, (
            f"BBox component {i}: got {a:.6g} expected {e:.6g} "
            f"(diff {abs(a-e):.2e} > tol {tol:.2e})"
        )


def assert_face_count(actual: int, expected: int) -> None:
    assert actual == expected, f"Face count: got {actual}, expected {expected}"


def assert_edge_count(actual: int, expected: int) -> None:
    assert actual == expected, f"Edge count: got {actual}, expected {expected}"


def assert_vertex_count(actual: int, expected: int) -> None:
    assert actual == expected, f"Vertex count: got {actual}, expected {expected}"


def assert_closed_shell(is_closed: bool) -> None:
    assert is_closed, "Shape shell is not closed (watertight check failed)"


def assert_center_of_mass(
    actual: tuple[float, float, float],
    expected: tuple[float, float, float],
    *,
    tol: float = _DEFAULT_LENGTH_TOL * 10,
) -> None:
    """Assert center-of-mass vector within *tol*."""
    err = math.sqrt(sum((a - e) ** 2 for a, e in zip(actual, expected)))
    assert err <= tol, (
        f"COM mismatch: got {actual} expected {expected} (dist {err:.4e} > tol {tol:.4e})"
    )


def assert_no_self_intersection(edge_count: int, vertex_count: int, face_count: int) -> None:
    """Euler characteristic check for a closed orientable surface: V - E + F = 2."""
    euler = vertex_count - edge_count + face_count
    assert euler == 2, (
        f"Euler characteristic {euler} != 2 (possible self-intersection or non-manifold)"
    )


# ---------------------------------------------------------------------------
# Code-string content assertions (used in Layer-A + Layer-B mock tests)
# ---------------------------------------------------------------------------

def assert_code_contains(code: str, *fragments: str) -> None:
    """Assert that *code* contains every fragment in *fragments*."""
    for frag in fragments:
        assert frag in code, f"Expected fragment {frag!r} not found in generated code"


def assert_code_compiles(code: str, filename: str = "<freecad-mcp-generated>") -> None:
    """Assert that *code* is valid Python syntax."""
    compile(code, filename, "exec")


# ---------------------------------------------------------------------------
# Gear-specific geometric invariants
# ---------------------------------------------------------------------------

def assert_involute_radius(
    x: float,
    y: float,
    t: float,
    r_b: float,
    *,
    tol: float = _DEFAULT_LENGTH_TOL,
) -> None:
    """Assert that point (x, y) lies on the involute of circle r_b at parameter t."""
    expected_x = r_b * (math.cos(t) + t * math.sin(t))
    expected_y = r_b * (math.sin(t) - t * math.cos(t))
    err = math.hypot(x - expected_x, y - expected_y)
    assert err <= tol, (
        f"Involute deviation at t={t:.4f}: ({x:.4f},{y:.4f}) vs ({expected_x:.4f},{expected_y:.4f}) "
        f"err={err:.2e} > tol={tol:.2e}"
    )


def assert_pitch_diameter(teeth: int, module: float, measured_diameter: float, *, tol: float = 1e-3) -> None:
    expected = teeth * module
    err = abs(measured_diameter - expected)
    assert err <= tol, (
        f"Pitch diameter: got {measured_diameter:.4f} expected {expected:.4f} (err {err:.4e})"
    )


def assert_addendum_diameter(teeth: int, module: float, measured_diameter: float, *, tol: float = 1e-3) -> None:
    expected = (teeth + 2) * module
    err = abs(measured_diameter - expected)
    assert err <= tol, (
        f"Addendum diameter: got {measured_diameter:.4f} expected {expected:.4f} (err {err:.4e})"
    )
