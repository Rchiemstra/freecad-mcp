"""Apply helpers for typed Assembly mutations. Apply never recomputes."""

from __future__ import annotations

from collections.abc import Mapping

from .typed_runtime import (
    TypedMutationError,
    is_derived_from,
    load_module,
    module_callable,
    object_label,
    object_name,
    require_object,
)


def _assembly_api() -> object:
    try:
        load_module("AssemblyApp")
    except TypedMutationError:
        pass
    return load_module("Assembly")


def _invalid_api_argument(exc: Exception) -> TypedMutationError | None:
    # Assembly.JointCreationError marks an argument the API refused, such as a
    # component outside the assembly; anything else is a genuine failure.
    if type(exc).__name__ == "JointCreationError":
        return TypedMutationError("INVALID_ARGUMENT", str(exc))
    return None


def require_assembly(document: object, name: str) -> object:
    assembly = require_object(document, name, code="ASSEMBLY_NOT_FOUND")
    if not is_derived_from(assembly, "Assembly::AssemblyObject"):
        raise TypedMutationError(
            "INVALID_ASSEMBLY",
            f"Object is not an Assembly::AssemblyObject: {name!r}",
        )
    return assembly


def joint_group_name(assembly: object, *, create_joint_group: bool) -> str | None:
    if not create_joint_group:
        return None
    utils = load_module("UtilsAssembly")
    getter = module_callable(utils, "getJointGroup")
    group = getter(assembly)
    name = object_name(group)
    return name or None


def create_assembly(
    document: object,
    *,
    assembly_name: str,
    create_joint_group: bool,
    if_exists: str,
) -> dict[str, str | None]:
    existing = None
    getter = getattr(document, "getObject", None)
    if callable(getter):
        existing = getter(assembly_name)
    if existing is not None:
        if if_exists == "error":
            raise TypedMutationError(
                "OBJECT_ALREADY_EXISTS",
                f"Object already exists: {assembly_name!r}",
            )
        if if_exists == "skip":
            if not is_derived_from(existing, "Assembly::AssemblyObject"):
                raise TypedMutationError(
                    "INVALID_ASSEMBLY",
                    f"Existing object is not an Assembly::AssemblyObject: {assembly_name!r}",
                )
            return {
                "assembly": object_name(existing),
                "label": object_label(existing),
                "type": str(getattr(existing, "TypeId", "")),
                "joint_group": joint_group_name(existing, create_joint_group=create_joint_group),
            }
        if if_exists == "replace":
            remover = getattr(document, "removeObject", None)
            if not callable(remover):
                raise TypedMutationError("INVALID_DOCUMENT", "document must provide removeObject")
            remover(object_name(existing))
        else:
            raise TypedMutationError("INVALID_ARGUMENT", "if_exists must be error, skip, or replace")

    create = module_callable(_assembly_api(), "createAssembly")
    assembly = create(
        document,
        assembly_name,
        createJointGroup=create_joint_group,
        recompute=False,
    )
    return {
        "assembly": object_name(assembly),
        "label": object_label(assembly),
        "type": str(getattr(assembly, "TypeId", "")),
        "joint_group": joint_group_name(assembly, create_joint_group=create_joint_group),
    }


def create_grounded_joint(
    document: object,
    *,
    assembly_name: str,
    component_name: str,
    label: str | None,
) -> dict[str, str]:
    assembly = require_assembly(document, assembly_name)
    component = require_object(document, component_name, code="COMPONENT_NOT_FOUND")
    create = module_callable(_assembly_api(), "createGroundedJoint")
    try:
        joint = create(assembly, component, label=label, recompute=False)
    except Exception as exc:
        raise (_invalid_api_argument(exc) or exc) from exc
    grounded = getattr(joint, "ObjectToGround", None)
    return {
        "joint": object_name(joint),
        "label": object_label(joint),
        "joint_type": "Grounded",
        "assembly": object_name(assembly),
        "component": object_name(grounded) if grounded is not None else object_name(component),
    }


def create_joint(
    document: object,
    *,
    assembly_name: str,
    joint_type: str,
    ref1_component: str,
    ref2_component: str,
    ref1_element: str,
    ref2_element: str,
    ref1_vertex: str | None,
    ref2_vertex: str | None,
    label: str | None,
    solve: bool,
    presolve: bool,
    properties: Mapping[str, object],
) -> dict[str, str]:
    assembly = require_assembly(document, assembly_name)
    ref1_obj = require_object(document, ref1_component, code="COMPONENT_NOT_FOUND")
    ref2_obj = require_object(document, ref2_component, code="COMPONENT_NOT_FOUND")
    api = _assembly_api()
    make_ref = module_callable(api, "makeJointReference")
    create = module_callable(api, "createJoint")
    try:
        ref1 = make_ref(ref1_obj, ref1_element, ref1_vertex)
        ref2 = make_ref(ref2_obj, ref2_element, ref2_vertex)
        joint = create(
            assembly,
            joint_type,
            ref1,
            ref2,
            label=label,
            solve=solve,
            presolve=presolve,
            recompute=False,
            **dict(properties),
        )
    except Exception as exc:
        raise (_invalid_api_argument(exc) or exc) from exc
    return {
        "joint": object_name(joint),
        "label": object_label(joint),
        "joint_type": str(getattr(joint, "JointType", joint_type)),
        "assembly": object_name(assembly),
    }


_SOLVE_FAILURES = {
    # The assembly Origin always counts as grounded, so -6 is rare in practice.
    -6: "the assembly has no grounded component; ground one with create_assembly_grounded_joint",
    -1: "the solver could not satisfy the joints; see the report view",
}


def solve_assembly(document: object, assembly_name: str) -> dict[str, str | None]:
    assembly = require_assembly(document, assembly_name)
    error: str | None = None
    solver = getattr(assembly, "solve", None)
    if callable(solver):
        try:
            status = solver()
        except Exception as exc:
            error = str(exc)
        else:
            # AssemblyObject::solve returns 0 on success and a negative code
            # when nothing was solved.
            if isinstance(status, int) and not isinstance(status, bool) and status != 0:
                reason = _SOLVE_FAILURES.get(status, "the solver reported a failure")
                raise TypedMutationError(
                    "ASSEMBLY_SOLVE_FAILED",
                    f"Solving {object_name(assembly)!r} failed (status {status}): {reason}",
                )
            return {
                "assembly": object_name(assembly),
                "method": "assembly.solve()",
                "status": str(status) if status is not None else None,
            }
    try:
        joint_object = load_module("JointObject")
        allowed = module_callable(joint_object, "solveIfAllowed")
        allowed(assembly, True)
        return {
            "assembly": object_name(assembly),
            "method": "JointObject.solveIfAllowed",
            "status": "ok",
        }
    except Exception as exc:
        combined = str(exc) if error is None else f"{error} | {exc}"
        raise TypedMutationError("SOLVE_UNAVAILABLE", f"solve_assembly failed: {combined}") from exc


__all__ = [
    "create_assembly",
    "create_grounded_joint",
    "create_joint",
    "require_assembly",
    "solve_assembly",
]
