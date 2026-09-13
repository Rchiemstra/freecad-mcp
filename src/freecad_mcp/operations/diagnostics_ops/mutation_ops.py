from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from ...template_resources import render_template_text
from ..p7_assembly import _run_json_code
from .helpers import _diag_preamble


def create_placement_binder_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    owner_body: str,
    name: str,
    source: str,
    relative: bool = True,
    bind_mode: str = "Synchronized",
) -> ToolResponse:
    code = [*_diag_preamble(doc_name), render_template_text(
        "diagnostics/create_placement_binder.py.txt",
        owner_body=repr(owner_body),
        binder_name=repr(name),
        source=repr(source),
        relative=repr(relative),
        bind_mode=repr(bind_mode),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to create placement-aware binder",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )

def create_placement_datum_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    owner_body: str,
    name: str,
    source: str,
    relative: bool = True,
    offset: list[float] | None = None,
) -> ToolResponse:
    code = [*_diag_preamble(doc_name), render_template_text(
        "diagnostics/create_placement_datum.py.txt",
        owner_body=repr(owner_body),
        datum_name=repr(name),
        source=repr(source),
        relative=repr(relative),
        offset=repr(offset or [0, 0, 0]),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to create placement-aware datum",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )

def run_transaction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> ToolResponse:
    """Fail closed: generated callbacks may not own native transaction control."""

    del freecad, only_text_feedback, doc_name, label, code, dry_run, commit_on_success
    return tool_fail(
        "run_transaction is retired because nested transaction control is incompatible "
        "with FreeCAD's native mutation coordinator; use typed modelling tools instead.",
        error_code="RUN_TRANSACTION_RETIRED",
        structured={
            "success": False,
            "ok": False,
            "error_code": "RUN_TRANSACTION_RETIRED",
            "error": (
                "Generated mutation callbacks cannot open, commit, abort, undo, or redo "
                "inside the native coordinator. Use typed modelling tools."
            ),
        },
    )

def validate_movement_follow_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    source: str,
    dependents: list[str],
    translation: list[float],
    axis: list[float],
    angle_deg: float,
    restore: bool = True,
    tolerance: float = 1e-7,
) -> ToolResponse:
    """Reject a two-recompute probe before it can alter the live document."""

    del (
        freecad,
        only_text_feedback,
        doc_name,
        source,
        dependents,
        translation,
        axis,
        angle_deg,
        restore,
        tolerance,
    )
    return tool_fail(
        "Movement-follow validation requires mutation work on both sides of "
        "recompute and cannot run atomically through the native coordinator.",
        error_code="UNSUPPORTED_NATIVE_PHASE_BOUNDARY",
        structured={
            "success": False,
            "ok": False,
            "error_code": "UNSUPPORTED_NATIVE_PHASE_BOUNDARY",
            "operation": "validate_movement_follow",
            "retryable": False,
        },
    )
