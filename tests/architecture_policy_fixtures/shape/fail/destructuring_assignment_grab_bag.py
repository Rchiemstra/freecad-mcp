"""Loop destructuring cannot hide mixed capability bindings."""

from capabilities.export.files import export_close as _export_close
from capabilities.mesh.topology import mesh_create as _mesh_create
from capabilities.sketch.geometry import sketch_create as _sketch_create

providers = [(object(), object(), object(), object(), object(), object(), object())]

for (
    sketch_create,
    sketch_update,
    mesh_create,
    mesh_update,
    export_open,
    export_save,
    export_close,
) in providers:
    _ = (
        sketch_create,
        sketch_update,
        mesh_create,
        mesh_update,
        export_open,
        export_save,
        export_close,
    )
