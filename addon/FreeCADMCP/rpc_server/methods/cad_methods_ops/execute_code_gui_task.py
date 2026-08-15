"""GUI-thread execute_code task (Phase 4 slice 4F)."""

from __future__ import annotations

import io
from contextlib import suppress
from typing import Any

from ...gui_dispatch import _flush_gui_events
from ._common import require_document_modified
from .execute_code_gui_exec import run_python_on_gui_thread
from .execute_code_gui_hooks import (
    install_read_only_save_hooks,
    recompute_documents,
    restore_active_document,
    restore_save_hooks,
)
from .execute_code_gui_session import build_execute_session, disk_signature
from .recompute_helpers import collect_invalid_objects

NATIVE_POST_RECOMPUTE_MARKER = "# __FREECAD_MCP_NATIVE_POST_RECOMPUTE__"


def _split_native_post_recompute_code(
    code: str,
    options: dict[str, Any],
    *,
    native_boundary: bool,
) -> tuple[str, str | None]:
    """Split a signed generated mutation from its read-only continuation.

    The marker is intentionally unavailable to public arbitrary execute_code.
    Generated callers authenticate the complete source before dispatch, so the
    apply and continuation halves remain bound to the same signed operation.
    """

    marker_count = code.count(NATIVE_POST_RECOMPUTE_MARKER)
    if marker_count == 0:
        return code, None
    if marker_count != 1:
        raise ValueError("generated code must contain exactly one native postcondition marker")
    if not options.get("generated_operation"):
        raise ValueError("native postcondition markers require a signed generated operation")
    if not native_boundary or options.get("recompute") != "target":
        raise ValueError(
            "native postcondition markers require one target document recompute"
        )
    apply_code, post_recompute_code = code.split(
        NATIVE_POST_RECOMPUTE_MARKER,
        1,
    )
    if not apply_code.strip() or not post_recompute_code.strip():
        raise ValueError("native postcondition marker requires apply and continuation code")
    return apply_code, post_recompute_code


def run_execute_code_gui_task(  # noqa: C901
    code: str,
    options: dict[str, Any],
    *,
    freecad,
    collect_invalid_objects_fn=None,
    native_boundary: bool = False,
    postcondition_sink: dict[str, Any] | None = None,
):
    output_buffer = io.StringIO()
    target_doc = options.get("document")
    recompute_mode = options.get("recompute", "none")
    recompute_docs = options.get("recompute_documents") or (
        [target_doc] if target_doc and recompute_mode == "target" else []
    )
    read_only = bool(options.get("read_only", False))
    restore_active = bool(options.get("restore_active_document", True))
    activate_doc = bool(options.get("activate_document", False))

    try:
        apply_code, post_recompute_code = _split_native_post_recompute_code(
            code,
            options,
            native_boundary=native_boundary,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "traceback": None,
            "session": {},
            "stdout": "",
        }

    active_before = freecad.ActiveDocument.Name if freecad.ActiveDocument else None
    dirty_before = {
        name: require_document_modified(doc)
        for name, doc in freecad.listDocuments().items()
    }
    disk_before = {
        name: disk_signature(doc) for name, doc in freecad.listDocuments().items()
    }
    collector = collect_invalid_objects_fn or collect_invalid_objects
    invalid_before = collector()

    if target_doc and activate_doc:
        doc = freecad.getDocument(target_doc)
        if doc:
            freecad.setActiveDocument(target_doc)

    saved_hooks: list = []
    read_only_unguarded: list[str] = []
    if read_only:
        saved_hooks, read_only_unguarded = install_read_only_save_hooks(
            freecad=freecad
        )

    ok = False
    tb_info = None
    try:
        ok, tb_info = run_python_on_gui_thread(
            apply_code, output_buffer, freecad=freecad
        )
    finally:
        restore_save_hooks(saved_hooks)
        if not native_boundary:
            recompute_documents(recompute_mode, recompute_docs, freecad=freecad)
        restore_active_document(active_before, restore_active, freecad=freecad)

    finalized_result: dict[str, Any] | None = None

    def finalize_result(*, flush_gui: bool) -> dict[str, Any]:
        nonlocal finalized_result, ok, tb_info
        if finalized_result is not None:
            return finalized_result
        if ok and post_recompute_code is not None:
            ok, tb_info = run_python_on_gui_thread(
                post_recompute_code,
                output_buffer,
                freecad=freecad,
            )
        if ok and not read_only and flush_gui:
            with suppress(Exception):
                _flush_gui_events()
        session = build_execute_session(
            target_doc=target_doc,
            active_before=active_before,
            dirty_before=dirty_before,
            disk_before=disk_before,
            invalid_before=invalid_before,
            read_only_unguarded=read_only_unguarded,
            freecad=freecad,
            collect_invalid_objects_fn=collect_invalid_objects_fn,
        )
        stdout = output_buffer.getvalue()
        if ok:
            finalized_result = {"ok": True, "session": session, "stdout": stdout}
        else:
            finalized_result = {
                "ok": False,
                "error": tb_info["message"] if tb_info else "Unknown error",
                "traceback": tb_info,
                "session": session,
                "stdout": stdout,
            }
        return finalized_result

    if ok and native_boundary and postcondition_sink is not None:
        # Session/error inspection that depends on recomputed geometry belongs
        # to the native read-only postcondition, after the coordinator's sole
        # eager recompute. GUI event delivery remains post-commit.
        postcondition_sink["finalize"] = lambda: finalize_result(flush_gui=False)
        return {"ok": True, "session": {}, "stdout": output_buffer.getvalue()}

    return finalize_result(flush_gui=not native_boundary)


__all__ = ["NATIVE_POST_RECOMPUTE_MARKER", "run_execute_code_gui_task"]
