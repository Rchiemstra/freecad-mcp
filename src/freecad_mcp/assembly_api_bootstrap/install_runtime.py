"""Install headless Assembly helpers into the runtime module."""

from __future__ import annotations

from .assembly_create import createAssembly
from .create_joint import createGroundedJoint, createJoint
from .headless_preferences import (
    bind_headless_module_registry,
    ensure_headless_preferences_shim,
)
from .joint_creation_error import JointCreationError
from .joint_reference import makeJointReference, referenceFromSelection

_EXPORTS = (
    "JointCreationError",
    "createAssembly",
    "createGroundedJoint",
    "createJoint",
    "makeJointReference",
    "referenceFromSelection",
)


def install(*, module_registry=None) -> None:
    """Expose headless Assembly helpers when the runtime Assembly module lacks them."""
    if module_registry is not None:
        bind_headless_module_registry(module_registry)
    ensure_headless_preferences_shim()
    import Assembly

    namespace = {
        "JointCreationError": JointCreationError,
        "createAssembly": createAssembly,
        "createGroundedJoint": createGroundedJoint,
        "createJoint": createJoint,
        "makeJointReference": makeJointReference,
        "referenceFromSelection": referenceFromSelection,
    }
    for name in _EXPORTS:
        if not hasattr(Assembly, name):
            setattr(Assembly, name, namespace[name])
