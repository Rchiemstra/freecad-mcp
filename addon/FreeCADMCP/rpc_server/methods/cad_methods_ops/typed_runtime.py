"""Shared runtime helpers for typed CAD mutations. No explicit ``Any``."""

from __future__ import annotations

import importlib
from typing import Protocol, cast


class TypedMutationError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DynCallable(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> object: ...


def as_str(value: object) -> str:
    return value if isinstance(value, str) else str(value)


def as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


def as_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return 0.0


def load_module(name: str) -> object:
    try:
        return importlib.import_module(name)
    except Exception as exc:
        raise TypedMutationError(
            "MISSING_DEPENDENCY",
            f"Required module {name!r} is not available: {exc}",
        ) from exc


def module_callable(module: object, name: str) -> DynCallable:
    value = getattr(module, name, None)
    if not callable(value):
        raise TypedMutationError(
            "MISSING_DEPENDENCY",
            f"Required callable {name!r} is not available",
        )
    return cast(DynCallable, value)


def require_object(document: object, name: str, *, code: str = "OBJECT_NOT_FOUND") -> object:
    getter = getattr(document, "getObject", None)
    if not callable(getter):
        raise TypedMutationError("INVALID_DOCUMENT", "document must provide getObject")
    found = getter(name)
    if found is None:
        raise TypedMutationError(code, f"Object not found: {name!r}")
    return found


def is_derived_from(obj: object, type_name: str) -> bool:
    checker = getattr(obj, "isDerivedFrom", None)
    if callable(checker):
        try:
            return bool(checker(type_name))
        except (AttributeError, TypeError, RuntimeError):
            return False
    return str(getattr(obj, "TypeId", "")) == type_name


def object_name(obj: object) -> str:
    return str(getattr(obj, "Name", ""))


def object_label(obj: object) -> str:
    return str(getattr(obj, "Label", object_name(obj)))


def require_nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypedMutationError("INVALID_ARGUMENT", f"{field} must be a nonempty string")
    return value


def require_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypedMutationError("INVALID_ARGUMENT", f"{field} must be a number")
    return float(value)


def require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypedMutationError("INVALID_ARGUMENT", f"{field} must be an integer")
    return value


def require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypedMutationError("INVALID_ARGUMENT", f"{field} must be a boolean")
    return value


__all__ = [
    "DynCallable",
    "TypedMutationError",
    "as_float",
    "as_int",
    "as_str",
    "is_derived_from",
    "load_module",
    "module_callable",
    "object_label",
    "object_name",
    "require_bool",
    "require_int",
    "require_nonempty_string",
    "require_number",
    "require_object",
]
