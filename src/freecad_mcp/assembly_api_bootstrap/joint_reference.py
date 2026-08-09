# SPDX-License-Identifier: LGPL-2.1-or-later

from .joint_creation_error import JointCreationError
from .validation import normalize_subname, require_assembly, require_component


def component_reference_from_selection(assembly, rootObj, subName, field):
    import UtilsAssembly

    subName = normalize_subname(subName, field)
    component, relative_sub = UtilsAssembly.getComponentReference(assembly, rootObj, subName)

    if component is None:
        component = rootObj
        relative_sub = subName

    component = require_component(component, assembly)
    relative_sub = normalize_subname(relative_sub, field)

    return component, relative_sub


def makeJointReference(component, element="", vertex=None):
    component = require_component(component)
    element = normalize_subname(element, "element")
    vertex = element if vertex is None else normalize_subname(vertex, "vertex")

    return [component, [element, vertex]]


def referenceFromSelection(assembly, rootObj, subName, vertexSubName=None):
    assembly = require_assembly(assembly)
    rootObj = require_component(rootObj, assembly)
    element_component, element = component_reference_from_selection(
        assembly, rootObj, subName, "subName"
    )

    if vertexSubName is None:
        vertex_component = element_component
        vertex = element
    else:
        vertex_component, vertex = component_reference_from_selection(
            assembly, rootObj, vertexSubName, "vertexSubName"
        )

    if vertex_component != element_component:
        raise JointCreationError("Selection element and vertex resolve to different components")

    return makeJointReference(element_component, element, vertex)
