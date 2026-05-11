"""
Layer-C curve-math helpers.

Sample N points analytically and compare to generated edge points.
All functions are pure Python — no FreeCAD dependency required for unit tests.
"""
from __future__ import annotations

import math
from typing import Callable


_DEFAULT_TOL = 1e-4  # mm


def linspace(start: float, stop: float, n: int) -> list[float]:
    """Return *n* evenly-spaced values in [start, stop]."""
    if n < 2:
        return [start]
    return [start + (stop - start) * i / (n - 1) for i in range(n)]


def sample_parametric(
    x_fn: Callable[[float], float],
    y_fn: Callable[[float], float],
    t_start: float,
    t_end: float,
    n: int = 50,
) -> list[tuple[float, float]]:
    """Return *n* (x, y) samples of a parametric curve."""
    return [(x_fn(t), y_fn(t)) for t in linspace(t_start, t_end, n)]


# ---------------------------------------------------------------------------
# Involute helpers
# ---------------------------------------------------------------------------

def involute_x(r_b: float, t: float) -> float:
    return r_b * (math.cos(t) + t * math.sin(t))


def involute_y(r_b: float, t: float) -> float:
    return r_b * (math.sin(t) - t * math.cos(t))


def involute_radius(r_b: float, t: float) -> float:
    return r_b * math.sqrt(1.0 + t * t)


def involute_polar_angle(t: float) -> float:
    """Polar angle of an involute point at parameter *t*: θ(t) = t - atan(t)."""
    return t - math.atan(t)


def involute_parameter_at_radius(r_b: float, r: float) -> float:
    """Return the involute parameter *t* such that the involute radius equals *r*."""
    if r < r_b:
        raise ValueError(f"r={r:.4f} < r_b={r_b:.4f}: radius inside base circle")
    return math.sqrt((r / r_b) ** 2 - 1.0)


def sample_involute(
    r_b: float,
    t_start: float,
    t_end: float,
    n: int = 50,
) -> list[tuple[float, float]]:
    """Sample the involute of circle *r_b* from parameter *t_start* to *t_end*."""
    return sample_parametric(
        lambda t: involute_x(r_b, t),
        lambda t: involute_y(r_b, t),
        t_start,
        t_end,
        n,
    )


# ---------------------------------------------------------------------------
# Assertion helpers (Layer C)
# ---------------------------------------------------------------------------

def assert_points_on_parametric(
    points: list[tuple[float, float]],
    x_fn: Callable[[float], float],
    y_fn: Callable[[float], float],
    t_start: float,
    t_end: float,
    *,
    tol: float = _DEFAULT_TOL,
) -> None:
    """For each point in *points* find nearest analytic sample and assert within *tol*."""
    n_analytic = max(len(points) * 4, 200)
    analytic = sample_parametric(x_fn, y_fn, t_start, t_end, n_analytic)

    for i, (px, py) in enumerate(points):
        nearest_dist = min(math.hypot(px - ax, py - ay) for ax, ay in analytic)
        assert nearest_dist <= tol, (
            f"Point[{i}] ({px:.4f},{py:.4f}) is {nearest_dist:.2e} mm from "
            f"nearest analytic sample (tol {tol:.2e})"
        )


def assert_involute_conformance(
    points: list[tuple[float, float]],
    r_b: float,
    t_start: float,
    t_end: float,
    *,
    tol: float = _DEFAULT_TOL,
) -> None:
    """Assert that *points* lie on the involute of *r_b* within *tol* mm."""
    assert_points_on_parametric(
        points,
        lambda t: involute_x(r_b, t),
        lambda t: involute_y(r_b, t),
        t_start,
        t_end,
        tol=tol,
    )


def assert_arc_conformance(
    points: list[tuple[float, float]],
    cx: float,
    cy: float,
    r: float,
    *,
    tol: float = _DEFAULT_TOL,
) -> None:
    """Assert that all *points* lie on a circle of radius *r* centred at (*cx*, *cy*)."""
    for i, (px, py) in enumerate(points):
        dist = math.hypot(px - cx, py - cy)
        err = abs(dist - r)
        assert err <= tol, (
            f"Arc point[{i}] ({px:.4f},{py:.4f}) radius error {err:.2e} > tol {tol:.2e}"
        )


def assert_ellipse_conformance(
    points: list[tuple[float, float]],
    cx: float,
    cy: float,
    a: float,
    b: float,
    *,
    tol: float = _DEFAULT_TOL,
) -> None:
    """Assert that all *points* lie on an ellipse with semi-axes *a* (X) and *b* (Y)."""
    for i, (px, py) in enumerate(points):
        val = ((px - cx) / a) ** 2 + ((py - cy) / b) ** 2
        err = abs(val - 1.0)
        assert err <= tol * 10, (
            f"Ellipse point[{i}] ({px:.4f},{py:.4f}) ellipse eq = {val:.6f} (err {err:.2e})"
        )


def assert_curve_closed(points: list[tuple[float, float]], *, tol: float = _DEFAULT_TOL) -> None:
    """Assert that the last point is within *tol* of the first."""
    if not points:
        return
    dist = math.hypot(points[-1][0] - points[0][0], points[-1][1] - points[0][1])
    assert dist <= tol, f"Curve not closed: gap = {dist:.4e} mm (tol {tol:.2e})"


def assert_monotone_radius(points: list[tuple[float, float]], cx: float = 0.0, cy: float = 0.0) -> None:
    """Assert that the radius from (cx, cy) is monotonically non-decreasing."""
    radii = [math.hypot(px - cx, py - cy) for px, py in points]
    for i in range(1, len(radii)):
        assert radii[i] >= radii[i - 1] - 1e-6, (
            f"Radius decreased at index {i}: {radii[i]:.4f} < {radii[i-1]:.4f}"
        )


def assert_on_involute_direct(
    points: list[tuple[float, float]],
    r_b: float,
    *,
    tol: float = 1e-10,
) -> None:
    """Exact involute conformance check for unrotated involutes.

    For each point (x, y), invert the involute radius formula to get the
    parameter t, then compare against the analytic formula directly.
    No grid search — machine-precision accurate for sample_involute output.
    Only valid for the *unrotated* involute (starting at (r_b, 0)).
    """
    for i, (x, y) in enumerate(points):
        r = math.hypot(x, y)
        if r < r_b - tol:
            raise AssertionError(
                f"Point[{i}] radius {r:.6f} < base_radius {r_b:.6f}"
            )
        t = math.sqrt(max(0.0, (r / r_b) ** 2 - 1.0))
        ex = r_b * (math.cos(t) + t * math.sin(t))
        ey = r_b * (math.sin(t) - t * math.cos(t))
        err = math.hypot(x - ex, y - ey)
        assert err <= tol, (
            f"Point[{i}] ({x:.6f},{y:.6f}) involute error {err:.2e} > tol {tol:.2e}"
        )
