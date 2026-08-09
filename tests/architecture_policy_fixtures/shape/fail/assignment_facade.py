"""Explicit assignment exports cannot hide mixed capability ownership."""

from capabilities.export.files import export_close as _export_close
from capabilities.mesh.topology import mesh_create as _mesh_create
from capabilities.sketch.geometry import sketch_create as _sketch_create


def _factory():
    return object()


sketch_tool01 = _factory()
mesh_tool02 = _factory()
sketch_tool03 = _factory()
mesh_tool04 = _factory()
sketch_tool05 = _factory()
mesh_tool06 = _factory()
sketch_tool07 = _factory()
mesh_tool08 = _factory()
sketch_tool09 = _factory()
mesh_tool10 = _factory()
sketch_tool11 = _factory()
mesh_tool12 = _factory()
sketch_tool13 = _factory()
mesh_tool14 = _factory()
sketch_tool15 = _factory()
sketch_tool16 = _factory()
sketch_tool17 = _factory()
mesh_tool18 = _factory()
sketch_tool19 = _factory()
mesh_tool20 = _factory()
sketch_tool21 = _factory()
sketch_tool22 = _factory()
sketch_tool23 = _factory()
mesh_tool24 = _factory()
