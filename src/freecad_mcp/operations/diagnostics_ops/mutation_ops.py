from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_text
from ..p7_assembly import _doc_preamble, _run_json_code
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
    preamble = _doc_preamble(doc_name)
    body = render_template_text(
        "diagnostics/run_transaction.py.txt",
        label=repr(label),
        code=repr(code),
        dry_run=repr(dry_run),
        commit_on_success=repr(commit_on_success),
    )
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(preamble) + "\n" + body,
        "Failed to run transaction",
        screenshot=True,
        document=doc_name,
        read_only=False,
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
    code = [*_diag_preamble(doc_name), render_template_text(
        "diagnostics/validate_movement_follow.py.txt",
        source=repr(source),
        dependents=repr(dependents),
        translation=repr(translation),
        axis=repr(axis),
        angle_deg=repr(angle_deg),
        restore=repr(restore),
        tolerance=repr(tolerance),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed movement-follow validation",
        screenshot=False,
        document=doc_name,
        read_only=False,
    )
