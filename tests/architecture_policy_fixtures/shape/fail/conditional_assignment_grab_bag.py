"""Conditional module bindings still own their capability subjects."""

from capabilities.export.files import export_close as _export_close
from capabilities.mesh.topology import mesh_create as _mesh_create
from capabilities.sketch.geometry import sketch_create as _sketch_create

ENABLED = True

if ENABLED:
    sketch_create = object()
    sketch_update = object()
    mesh_create = object()
    mesh_update = object()
    export_open = object()
    export_save = object()
    export_close = object()
