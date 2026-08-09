# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App

from .joint_creation_error import JointCreationError


def joint_type_index(jointType, jointTypes):
    if isinstance(jointType, int):
        if jointType < 0 or jointType >= len(jointTypes):
            raise JointCreationError("jointType index is out of range")
        return jointType

    if not isinstance(jointType, str):
        raise JointCreationError("jointType must be a string or index")

    if jointType not in jointTypes:
        expected = ", ".join(jointTypes)
        raise JointCreationError(
            f"Unsupported joint type '{jointType}'. Expected one of: {expected}"
        )

    return jointTypes.index(jointType)


def apply_joint_properties(joint, properties):
    property_names = set(getattr(joint, "PropertiesList", []))

    for name, value in properties.items():
        if name == "JointType":
            raise JointCreationError("JointType is controlled by the jointType argument")

        if name not in property_names:
            raise JointCreationError(f"Unknown joint property '{name}'")

        try:
            setattr(joint, name, value)
        except Exception as exc:
            raise JointCreationError(f"Unable to set joint property '{name}': {exc}") from exc


def attach_joint_view_provider(joint, grounded):
    if not App.GuiUp:
        return

    view_object = getattr(joint, "ViewObject", None)
    if view_object is None:
        return

    import JointObject

    if grounded:
        JointObject.ViewProviderGroundedJoint(view_object)
    else:
        JointObject.ViewProviderJoint(view_object)
