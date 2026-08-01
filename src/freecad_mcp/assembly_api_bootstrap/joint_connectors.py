# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App


def set_joint_connectors(joint, refs, *, solve, presolve):
    try:
        joint.Proxy.setJointConnectors(joint, refs, solve=solve, presolve=presolve)
    except TypeError:
        set_joint_connectors_legacy(joint, refs, solve=solve, presolve=presolve)


def set_joint_connectors_legacy(joint, refs, *, solve, presolve):
    import JointObject

    proxy = joint.Proxy
    assembly = proxy.getAssembly(joint)
    is_assembly = assembly.Type == "Assembly"

    if len(refs) >= 1:
        joint.Reference1 = refs[0]
    else:
        joint.Reference1 = None
        joint.Placement1 = App.Placement()
        proxy.partMovedByPresolved = None

    if len(refs) >= 2:
        joint.Reference2 = refs[1]
        proxy.ensureUnconnectedIsSecondRef(joint)

        if presolve and joint.JointType in JointObject.JointUsingPreSolve:
            proxy.preSolve(joint)
        elif presolve and joint.JointType in JointObject.JointParallelForbidden:
            proxy.preventParallel(joint)

        if is_assembly and solve:
            JointObject.solveIfAllowed(assembly, True)
        else:
            proxy.updateJCSPlacements(joint)
    else:
        joint.Reference2 = None
        joint.Placement2 = App.Placement()
        if is_assembly and solve:
            assembly.undoSolve()
        proxy.undoPreSolve(joint)
