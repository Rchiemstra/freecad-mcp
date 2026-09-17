"""Shared runtime helpers for policy-specific typed RPC executors."""

from __future__ import annotations

import os
from typing import cast


def app_from(collaborators: object) -> object | None:
    return getattr(collaborators, "freecad", None)


def document_id(document: object) -> str:
    if isinstance(document, str) and document.strip():
        return document
    name = getattr(document, "Name", None)
    if isinstance(name, str) and name.strip():
        return name
    raise TypeError(f"document id must be str, not {type(document).__name__}")


def lookup_document(app: object, name: object) -> object | None:
    if name is not None and not isinstance(name, str):
        existing = getattr(name, "Name", None)
        if isinstance(existing, str) and existing.strip():
            return name
        return None
    getter = getattr(app, "getDocument", None)
    if not callable(getter) or not isinstance(name, str):
        return None
    try:
        return cast(object | None, getter(name))
    except NameError:
        return None


def lookup_object(document: object, name: str) -> object | None:
    getter = getattr(document, "getObject", None)
    if not callable(getter):
        return None
    return cast(object | None, getter(name))


def optional_recompute(collaborators: object, document: object) -> None:
    runner = getattr(collaborators, "recompute_and_wait", None)
    if callable(runner):
        if isinstance(document, str) and document.strip():
            runner(document)
            return
        name = getattr(document, "Name", None)
        if isinstance(name, str) and name.strip():
            runner(name)
            return
    recompute = getattr(document, "recompute", None)
    if callable(recompute):
        recompute()


def atomic_publish(tmp_path: str, dest_path: str) -> None:
    os.replace(tmp_path, dest_path)


def staged_path(file_path: str) -> str:
    root, ext = os.path.splitext(file_path)
    if ext:
        return f"{root}.tmp{ext}"
    return f"{file_path}.tmp"


def verify_nonempty_file(path: str) -> bool:
    return os.path.isfile(path) and os.path.getsize(path) > 0


def unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


__all__ = [
    "app_from",
    "atomic_publish",
    "document_id",
    "lookup_document",
    "lookup_object",
    "optional_recompute",
    "staged_path",
    "unlink_quiet",
    "verify_nonempty_file",
]
