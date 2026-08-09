# SPDX-License-Identifier: LGPL-2.1-or-later

from .headless_preferences import ensure_headless_preferences_shim
from .joint_connectors import set_joint_connectors
from .joint_properties import apply_joint_properties, attach_joint_view_provider, joint_type_index
from .validation import normalize_reference, require_assembly, require_component


def createJoint(
    assembly,
    jointType,
    ref1,
    ref2,
    *,
    label=None,
    solve=True,
    presolve=True,
    recompute=True,
    **properties,
):
    ensure_headless_preferences_shim()

    import JointObject
    import UtilsAssembly

    assembly = require_assembly(assembly)
    ref1 = normalize_reference(ref1, assembly, "ref1")
    ref2 = normalize_reference(ref2, assembly, "ref2")
    type_index = joint_type_index(jointType, JointObject.JointTypes)

    if recompute:
        assembly.Document.recompute()

    if getattr(assembly, "Type", None) == "Assembly":
        assembly.ensureIdentityPlacements()

    joint_group = UtilsAssembly.getJointGroup(assembly)
    joint = joint_group.newObject("App::FeaturePython", "Joint")
    JointObject.Joint(joint, type_index)
    joint.Label = JointObject.JointTypes[type_index] if label is None else label
    attach_joint_view_provider(joint, grounded=False)

    apply_joint_properties(joint, properties)
    set_joint_connectors(joint, [ref1, ref2], solve=bool(solve), presolve=bool(presolve))

    if recompute:
        assembly.Document.recompute()

    return joint


def createGroundedJoint(assembly, component, *, label=None, recompute=True):
    ensure_headless_preferences_shim()

    import JointObject
    import UtilsAssembly

    assembly = require_assembly(assembly)
    component = require_component(component, assembly)

    joint_group = UtilsAssembly.getJointGroup(assembly)
    joint = joint_group.newObject("App::FeaturePython", "GroundedJoint")
    JointObject.GroundedJoint(joint, component)
    if label is not None:
        joint.Label = label
    attach_joint_view_provider(joint, grounded=True)

    if recompute:
        assembly.Document.recompute()

    return joint
