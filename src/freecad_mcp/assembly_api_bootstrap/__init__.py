# SPDX-License-Identifier: LGPL-2.1-or-later

from .assembly_create import createAssembly
from .create_joint import createGroundedJoint, createJoint
from .headless_preferences import (
    bind_headless_module_registry,
    ensure_headless_preferences_shim,
)
from .joint_creation_error import JointCreationError
from .joint_reference import makeJointReference, referenceFromSelection

__all__ = [
    "JointCreationError",
    "createAssembly",
    "createGroundedJoint",
    "createJoint",
    "makeJointReference",
    "referenceFromSelection",
]


def install(*, module_registry=None):
    """Expose headless Assembly helpers when the runtime Assembly module lacks them."""
    if module_registry is not None:
        bind_headless_module_registry(module_registry)
    ensure_headless_preferences_shim()
    import Assembly

    for name in __all__:
        if not hasattr(Assembly, name):
            setattr(Assembly, name, globals()[name])
