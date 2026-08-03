"""Conditional module bindings still own their capability subjects."""

ENABLED = True

if ENABLED:
    sketch_create = object()
    sketch_update = object()
    mesh_create = object()
    mesh_update = object()
    export_open = object()
    export_save = object()
    export_close = object()
