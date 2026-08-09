"""Native apply/render/restore orchestration for personal contexts."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from .collaboration_context_core import (
    _document_name,
    _member,
    collaborators,
    request_actor,
    resolve_document,
)
from .collaboration_context_dispatch import dispatch_gui
from .collaboration_context_view import build_view_context


def render_temporary_context_gui(
    facade: Any,
    document_name: str,
    actor: str,
    context: Mapping[str, Any],
    width: int = -1,
    height: int = -1,
    background: str = "Current",
    samples: int = -1,
) -> bytes:
    collabs = collaborators(facade)
    snapshot = _member(collabs, "snapshot_personal_view_context")(document_name, actor)
    try:
        _member(collabs, "store_personal_view_context")(
            document_name, actor, dict(context)
        )
        image = _member(collabs, "render_personal_view_context")(
            document_name,
            actor,
            width,
            height,
            background,
            samples,
        )
    except Exception as primary:
        try:
            _member(collabs, "restore_personal_view_context")(
                document_name, actor, snapshot
            )
        except Exception as restore_error:
            primary.add_note(f"personal view restore also failed: {restore_error}")
        raise
    else:
        _member(collabs, "restore_personal_view_context")(
            document_name, actor, snapshot
        )
        return image


def render_personal_context(
    facade: Any,
    *,
    hint: Any = None,
    view_name: str | None = None,
    focus_object: str | None = None,
    focus_objects: Any = None,
    yaw_deg: float | None = None,
    fit: bool | None = None,
    width: int | None = None,
    height: int | None = None,
    background: str = "Current",
    samples: int = -1,
) -> tuple[bytes, dict[str, Any]]:
    actor = request_actor(facade)

    def render() -> tuple[bytes, dict[str, Any]]:
        return render_personal_context_gui(
            facade,
            actor=actor,
            hint=hint,
            view_name=view_name,
            focus_object=focus_object,
            focus_objects=focus_objects,
            yaw_deg=yaw_deg,
            fit=fit,
            width=width,
            height=height,
            background=background,
            samples=samples,
        )

    return dispatch_gui(facade, render)


def render_personal_context_gui(
    facade: Any,
    *,
    actor: str,
    hint: Any = None,
    view_name: str | None = None,
    focus_object: str | None = None,
    focus_objects: Any = None,
    yaw_deg: float | None = None,
    fit: bool | None = None,
    width: int | None = None,
    height: int | None = None,
    background: str = "Current",
    samples: int = -1,
) -> tuple[bytes, dict[str, Any]]:
    """Render an actor context while the caller already owns the GUI thread.

    This intentionally performs no dispatch.  It is for GUI callbacks that need
    to combine a native mutation and personal-context render atomically.
    """
    document = resolve_document(facade, actor, hint)
    context = build_view_context(
        facade,
        document,
        actor,
        view_name=view_name,
        focus_object=focus_object,
        focus_objects=focus_objects,
        yaw_deg=yaw_deg,
        fit=fit,
        width=width,
        height=height,
    )
    image = render_temporary_context_gui(
        facade,
        _document_name(document),
        actor,
        context,
        -1 if width is None else int(width),
        -1 if height is None else int(height),
        background,
        int(samples),
    )
    return image, context


def encode_png_bytes(image: bytes | bytearray | memoryview) -> str:
    if not isinstance(image, (bytes, bytearray, memoryview)):
        raise TypeError("native renderer did not return PNG bytes")
    return base64.b64encode(bytes(image)).decode("ascii")


__all__ = [
    "encode_png_bytes",
    "render_personal_context",
    "render_personal_context_gui",
    "render_temporary_context_gui",
]
