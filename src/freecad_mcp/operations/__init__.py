"""Operations barrel — public re-exports for server.py and tools_*."""

from __future__ import annotations

from . import (
    core,
    diagnostics,
    interactive,
    legacy_locking_deprecations,
    p1_curves,
    p2_editing,
    p3_features,
    p4_gears,
    p5_measure,
    p6_io,
    p7_assembly,
    parametric,
    snapshot,
    video_anim,
)

_SUBMODULES = (
    core,
    diagnostics,
    interactive,
    legacy_locking_deprecations,
    p1_curves,
    p2_editing,
    p3_features,
    p4_gears,
    p5_measure,
    p6_io,
    p7_assembly,
    parametric,
    snapshot,
    video_anim,
)

_BARREL_EXCLUDE = frozenset(
    {
        "solve_assembly_operation",
        "validate_movement_follow_operation",
    }
)

__all__: list[str] = []
for _module in _SUBMODULES:
    for _name in _module.__all__:
        if _name.startswith("_") or _name in _BARREL_EXCLUDE:
            continue
        if _name in __all__:
            continue
        globals()[_name] = getattr(_module, _name)
        __all__.append(_name)

from .p7_assembly import solve_assembly_operation  # noqa: E402, F401 - §3.3 shim
from .parametric_ops.validate_movement_follow import (  # noqa: E402
    validate_movement_follow_operation,
)

# Public MCP/JSON-RPC route keeps main's movement-follow contract. The
# diagnostics.mutation_ops helper stays fail-closed for generated two-recompute
# probes that cannot run atomically through the native coordinator.
__all__.append("validate_movement_follow_operation")
