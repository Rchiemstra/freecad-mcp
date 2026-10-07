"""Post-recompute check that an assigned property kept its value.

``set_object_property`` converts JSON before assigning it: an object name becomes the
document object, a dict becomes a ``Placement`` or ``Vector``. The check converts the
expected value the same way, so it compares like with like instead of JSON with FreeCAD.

An ``App::PropertyFileIncluded`` (for example ``Image::ImagePlane.ImageFile``) never reads
back the assigned path: FreeCAD copies the file into the document's transient directory
and the property holds the copy's path. The check compares the copy with the assigned file.
"""

from __future__ import annotations

import filecmp
import os
from collections.abc import Mapping

_TOLERANCE = 1e-6
_FILE_INCLUDED = "App::PropertyFileIncluded"


class IncludedFile:
    """Read-back of an ``App::PropertyFileIncluded``: the path of FreeCAD's transient copy."""

    __slots__ = ("path",)

    def __init__(self, path: str) -> None:
        self.path = path

    def __repr__(self) -> str:
        return f"IncludedFile({self.path!r})"


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


def _property_type(obj: object, key: str) -> object:
    getter = getattr(obj, "getTypeIdOfProperty", None)
    if not callable(getter):
        return None
    try:
        return getter(key)
    except Exception:  # noqa: BLE001 - dynamic or removed property: no type to report
        return None


def _included_file_kept(expected: object, kept: IncludedFile) -> bool:
    if not isinstance(expected, (str, os.PathLike)):
        return False
    source = os.fspath(expected)
    if not source:
        return not kept.path
    if not kept.path or not os.path.isfile(kept.path):
        return False
    if os.path.isfile(source):
        try:
            return os.path.samefile(source, kept.path) or filecmp.cmp(
                source, kept.path, shallow=False
            )
        except OSError:
            return False
    # A file that already lived in the transient directory is moved, not copied.
    return os.path.basename(source) == os.path.basename(kept.path)


def kept_property(obj: object, key: str) -> object:
    """The value ``obj.key`` holds after recompute, where FreeCAD keeps it elsewhere.

    A Link array with ShowElement true moves a PlacementList set before ElementCount onto its
    element objects and clears the list, so the layout is read back from the elements.
    A file-included property holds the path of a transient copy (see ``IncludedFile``).
    """
    value = getattr(obj, key)
    if isinstance(value, str) and _property_type(obj, key) == _FILE_INCLUDED:
        return IncludedFile(value)
    elements = list(getattr(obj, "ElementList", None) or []) if key == "PlacementList" else []
    if elements and getattr(obj, "ShowElement", False) is True:
        return [getattr(element, "Placement", None) for element in elements]
    return value


def property_kept_value(doc: object, expected: object, actual: object) -> bool:
    if isinstance(actual, IncludedFile):
        return _included_file_kept(expected, actual)
    if isinstance(expected, list) and isinstance(actual, (list, tuple)):
        # List properties (e.g. PlacementList) are converted element by element.
        return len(expected) == len(actual) and all(
            property_kept_value(doc, item, kept) for item, kept in zip(expected, actual)
        )
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


__all__ = ["IncludedFile", "kept_property", "property_kept_value"]
