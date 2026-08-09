"""Explicit assignment exports cannot hide mixed capability ownership."""

from capabilities.export.files import export_close as _export_close
from capabilities.export.files import export_open as _export_open
from capabilities.export.files import export_save as _export_save
from capabilities.mesh.topology import mesh_create as _mesh_create
from capabilities.mesh.topology import mesh_update as _mesh_update
from capabilities.sketch.geometry import sketch_create as _sketch_create
from capabilities.sketch.geometry import sketch_update as _sketch_update


def _factory():
    return object()


sketch_create = _factory()
sketch_update = _factory()
mesh_create = _factory()
mesh_update = _factory()
export_open = _factory()
export_save = _factory()
export_close = _factory()
