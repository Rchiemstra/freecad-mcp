"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_model_ops as _generated,
)

sketch_attach = _generated.sketch_attach
sketch_edit_constraint = _generated.sketch_edit_constraint
diagnose_parametric = _generated.diagnose_parametric
recompute_document = _generated.recompute_document
undo = _generated.undo
redo = _generated.redo
run_fem_analysis = _generated.run_fem_analysis
get_mutation_readiness = _generated.get_mutation_readiness

__all__ = [  # noqa: RUF022
    'sketch_attach',
    'sketch_edit_constraint',
    'diagnose_parametric',
    'recompute_document',
    'undo',
    'redo',
    'run_fem_analysis',
    'get_mutation_readiness',
]
