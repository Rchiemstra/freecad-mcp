"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_sketch_ops as _generated,
)

sketch_create = _generated.sketch_create
sketch_add_geometry = _generated.sketch_add_geometry
sketch_add_constraint = _generated.sketch_add_constraint
sketch_delete_constraint = _generated.sketch_delete_constraint
sketch_delete_geometry = _generated.sketch_delete_geometry
pad_feature = _generated.pad_feature
pocket_feature = _generated.pocket_feature

__all__ = [  # noqa: RUF022
    'sketch_create',
    'sketch_add_geometry',
    'sketch_add_constraint',
    'sketch_delete_constraint',
    'sketch_delete_geometry',
    'pad_feature',
    'pocket_feature',
]
