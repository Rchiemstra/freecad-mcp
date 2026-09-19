"""Post-recompute check that an assigned property kept its value.

``set_object_property`` converts JSON before assigning it: an object name becomes the
document object, a dict becomes a ``Placement`` or ``Vector``. The check converts the
expected value the same way, so it compares like with like instead of JSON with FreeCAD.
"""

from __future__ import annotations

from collections.abc import Mapping

_TOLERANCE = 1e-6


def _scalar(value: object) -> object:
    return getattr(value, "Value", value)


def _is_placement(value: object) -> bool:
    return hasattr(value, "Base") and hasattr(value, "Rotation") and hasattr(value, "isSame")


def _is_vector(value: object) -> bool:
    return all(hasattr(value, axis) for axis in ("x", "y", "z")) and hasattr(value, "Length")


def _converted_expected(doc: object, expected: object, actual: object) -> object:
    if isinstance(expected, str) and not isinstance(actual, str) and hasattr(actual, "Name"):
        getter = getattr(doc, "getObject", None)
        referenced = getter(expected) if callable(getter) else None
        return referenced if referenced is not None else expected
    if isinstance(expected, Mapping) and (_is_placement(actual) or _is_vector(actual)):
        try:
            from ...placement_codec import _as_vector, dict_to_placement
        except ImportError:  # pragma: no cover - flat addon import path
            from placement_codec import _as_vector, dict_to_placement
        return dict_to_placement(dict(expected)) if _is_placement(actual) else _as_vector(dict(expected))
    return expected


def property_kept_value(doc: object, expected: object, actual: object) -> bool:
    expected = _converted_expected(doc, expected, actual)
    left, right = _scalar(expected), _scalar(actual)
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= _TOLERANCE
    if _is_placement(left) and _is_placement(right):
        return bool(left.isSame(right, _TOLERANCE))  # type: ignore[attr-defined]
    if _is_vector(left) and _is_vector(right):
        return bool((left - right).Length <= _TOLERANCE)  # type: ignore[operator]
    if left is right:
        return True
    return bool(left == right)


__all__ = ["property_kept_value"]
