# SPDX-License-Identifier: LGPL-2.1-or-later

from .assembly_create import createAssembly
from .create_joint import createGroundedJoint, createJoint
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


def install():
    """Expose headless Assembly helpers when the runtime Assembly module lacks them."""
    import Assembly

    for name in __all__:
        if not hasattr(Assembly, name):
            setattr(Assembly, name, globals()[name])
