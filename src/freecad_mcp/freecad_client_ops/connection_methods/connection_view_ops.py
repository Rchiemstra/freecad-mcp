"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_view_ops as _generated,
)

get_active_screenshot = _generated.get_active_screenshot
capture_view_sequence = _generated.capture_view_sequence
capture_view_sequence_to_disk = _generated.capture_view_sequence_to_disk
refresh_view = _generated.refresh_view
repair_view_placements = _generated.repair_view_placements
animate_placement = _generated.animate_placement
get_objects = _generated.get_objects
get_object = _generated.get_object
get_parts_list = _generated.get_parts_list
list_documents = _generated.list_documents
open_document = _generated.open_document
activate_document = _generated.activate_document
set_tree_expanded = _generated.set_tree_expanded
select_subshapes = _generated.select_subshapes


def get_selection(conn):
    routed = conn._invoke_mutation_v2(
        "get_selection",
        {},
        operation_name="Get selection",
    )
    if routed is not None:
        return routed
    return _generated.get_selection(conn)


def get_gui_state(conn):
    routed = conn._invoke_mutation_v2(
        "get_gui_state",
        {},
        operation_name="Get GUI state",
    )
    if routed is not None:
        return routed
    return _generated.get_gui_state(conn)


def get_report_view(conn, max_lines: int | None = 200, clear: bool = False):
    routed = conn._invoke_mutation_v2(
        "get_report_view",
        {"max_lines": max_lines, "clear": clear},
        operation_name="Get Report view",
    )
    if routed is not None:
        return routed
    return _generated.get_report_view(conn, max_lines=max_lines, clear=clear)


recompute_and_wait = _generated.recompute_and_wait
set_section_view = _generated.set_section_view

__all__ = [  # noqa: RUF022
    'get_active_screenshot',
    'capture_view_sequence',
    'capture_view_sequence_to_disk',
    'refresh_view',
    'repair_view_placements',
    'animate_placement',
    'get_objects',
    'get_object',
    'get_parts_list',
    'list_documents',
    'open_document',
    'activate_document',
    'set_tree_expanded',
    'select_subshapes',
    'get_selection',
    'get_gui_state',
    'get_report_view',
    'recompute_and_wait',
    'set_section_view',
]
