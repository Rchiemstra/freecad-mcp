"""Loop destructuring cannot hide mixed capability bindings."""

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
