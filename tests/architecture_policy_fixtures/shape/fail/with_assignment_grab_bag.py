"""With-statement targets remain module-owned capability bindings."""


class _Factory:
    def __enter__(self):
        return (object(), object(), object(), object(), object(), object(), object())

    def __exit__(self, exc_type, exc, traceback):
        return False


with _Factory() as (
    sketch_create,
    sketch_update,
    mesh_create,
    mesh_update,
    export_open,
    export_save,
    export_close,
):
    pass
