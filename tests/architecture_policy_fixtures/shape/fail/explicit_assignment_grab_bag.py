"""Explicit assignment exports cannot hide mixed capability ownership."""


def _factory():
    return object()


sketch_create = _factory()
sketch_update = _factory()
mesh_create = _factory()
mesh_update = _factory()
export_open = _factory()
export_save = _factory()
export_close = _factory()

__all__ = (
    "export_close",
    "export_open",
    "export_save",
    "mesh_create",
    "mesh_update",
    "sketch_create",
    "sketch_update",
)
