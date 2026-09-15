"""Shared runtime helpers for policy-specific typed RPC executors."""

from __future__ import annotations

import os
from typing import cast


def app_from(collaborators: object) -> object | None:
    return getattr(collaborators, "freecad", None)


def lookup_document(app: object, name: str) -> object | None:
    getter = getattr(app, "getDocument", None)
    if not callable(getter):
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
        runner(document)
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
    "lookup_document",
    "lookup_object",
    "optional_recompute",
    "staged_path",
    "unlink_quiet",
    "verify_nonempty_file",
]
