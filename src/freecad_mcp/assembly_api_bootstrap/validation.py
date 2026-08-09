# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App

from .joint_creation_error import JointCreationError


def require_document(doc):
    if doc is None:
        doc = App.ActiveDocument

    if doc is None:
        raise JointCreationError("No active document; pass a document explicitly")

    if not hasattr(doc, "addObject"):
        raise JointCreationError("doc must be a FreeCAD document")

    return doc


def require_assembly(assembly):
    if assembly is None or not hasattr(assembly, "isDerivedFrom"):
        raise JointCreationError("assembly must be an Assembly::AssemblyObject")

    if not assembly.isDerivedFrom("Assembly::AssemblyObject"):
        raise JointCreationError("assembly must be an Assembly::AssemblyObject")

    if getattr(assembly, "Document", None) is None:
        raise JointCreationError("assembly must belong to a document")

    return assembly


def require_component(component, assembly=None):
    if component is None or not hasattr(component, "Name"):
        raise JointCreationError("component must be a FreeCAD document object")

    if getattr(component, "Document", None) is None:
        raise JointCreationError("component must belong to a document")

    if assembly is not None and component.Document != assembly.Document:
        raise JointCreationError("component must belong to the same document as the assembly")

    return component


def normalize_subname(subname, field):
    if subname is None:
        subname = ""

    if not isinstance(subname, str):
        raise JointCreationError(f"{field} must be a string")

    if "?" in subname:
        raise JointCreationError(f"{field} contains an unresolved subelement name")

    return subname


def normalize_reference(ref, assembly, field):
    if not isinstance(ref, (list, tuple)) or len(ref) != 2:
        raise JointCreationError(f"{field} must be [component, [element, vertex]]")

    component = require_component(ref[0], assembly)
    subnames = ref[1]
    if not isinstance(subnames, (list, tuple)) or len(subnames) != 2:
        raise JointCreationError(f"{field} must contain exactly two subelement names")

    element = normalize_subname(subnames[0], f"{field} element")
    vertex = normalize_subname(subnames[1], f"{field} vertex")

    return [component, [element, vertex]]
