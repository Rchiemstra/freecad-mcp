"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

from ...property_mapper import Object
from .cad_mutation import run_cad_mutation


def _split_presentation_properties(properties):
    model_properties = dict(properties)
    presentation_properties = {
        name: model_properties.pop(name)
        for name in ("ShapeColor", "ViewObject")
        if name in model_properties
    }
    return model_properties, presentation_properties


def create_object(self, doc_name, obj_data: dict[str, Any]):
    properties, presentation_properties = _split_presentation_properties(
        obj_data.get("Properties", {})
    )
    obj = Object(
        name=obj_data.get("Name", "New_Object"),
        type=obj_data["Type"],
        analysis=obj_data.get("Analysis"),
        properties=properties,
    )
    collaborators = self._cad_collaborators

    def create_task():
        deferred_presentation = None

        def create_model():
            nonlocal deferred_presentation
            result = collaborators.create_object_gui(doc_name, obj)
            apply_after_commit = getattr(result, "apply_after_commit", None)
            if callable(apply_after_commit):
                deferred_presentation = apply_after_commit
                return True
            return result

        result = run_cad_mutation(
            collaborators, doc_name,
            create_model,
            structural=True,
        )
        if result is True and deferred_presentation is not None:
            try:
                deferred_presentation()
            except Exception as exc:
                return str(exc)
        if result is True and presentation_properties:
            document = collaborators.freecad.getDocument(doc_name)
            created = document.getObject(obj.name) if document else None
            if created is None:
                return f"Object '{obj.name}' was not visible after native commit."
            try:
                collaborators.set_object_property(
                    document, created, presentation_properties
                )
            except Exception as exc:
                return str(exc)
        return result

    res = self._dispatch_gui(create_task)
    return self._adapt_gui_mutation_result(
        res, success_fields={"object_name": obj.name}
    )


def edit_object(
    self, doc_name: str, obj_name: str, properties: dict[str, Any]
) -> dict[str, Any]:
    model_properties, presentation_properties = _split_presentation_properties(
        properties.get("Properties", {})
    )
    obj = Object(
        name=obj_name,
        properties=model_properties,
    )
    collaborators = self._cad_collaborators

    def edit_task():
        # Property edits can trigger Assembly solve / dynamic-property work
        # during the in-callback recompute; declare structural so the grant
        # covers that window (same as create/delete).
        result = run_cad_mutation(
            collaborators, doc_name,
            lambda: edit_object_gui(
                doc_name, obj, freecad=collaborators.freecad,
                set_object_property=collaborators.set_object_property,
            ),
            structural=True,
        )
        if result is True and presentation_properties:
            document = collaborators.freecad.getDocument(doc_name)
            edited = document.getObject(obj.name) if document else None
            if edited is None:
                return f"Object '{obj.name}' was not visible after native commit."
            try:
                collaborators.set_object_property(
                    document, edited, presentation_properties
                )
            except Exception as exc:
                return str(exc)
        return result

    res = self._dispatch_gui(edit_task)
    return self._adapt_gui_mutation_result(
        res, success_fields={"object_name": obj.name}
    )


def delete_object(self, doc_name: str, obj_name: str):
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators, doc_name,
            lambda: delete_object_gui(
                doc_name, obj_name, freecad=collaborators.freecad
            ),
            structural=True,
        )
    )
    return self._adapt_gui_mutation_result(
        res, success_fields={"object_name": obj_name}
    )


def get_objects(self, doc_name):
    # Must run in the GUI thread: serialize_object accesses ViewObject
    # and other GUI-backed properties that FreeCAD guards against
    # access from background threads.
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: get_objects_gui(
            doc_name,
            freecad=collaborators.freecad,
            serialize_object=collaborators.serialize_object,
        )
    )
    if isinstance(res, list):
        return res
    return []


def get_object(self, doc_name, obj_name):
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: get_object_gui(
            doc_name, obj_name,
            freecad=collaborators.freecad,
            serialize_object=collaborators.serialize_object,
        )
    )
    # False sentinel means "not found"; timeout string → None
    if res is False or isinstance(res, str):
        return None
    return res


def insert_part_from_library(self, doc_name, relative_path):
    collaborators = self._cad_collaborators

    def insert_part_task():
        return run_cad_mutation(
            collaborators, doc_name,
            lambda: insert_part_from_library_gui(
                doc_name,
                relative_path,
                insert_part_from_library=collaborators.insert_part_from_library,
            ),
            structural=True,
        )

    res = self._dispatch_gui(insert_part_task)
    return self._adapt_gui_mutation_result(
        res,
        success_fields={"message": "Part inserted from library."},
    )


def edit_object_gui(doc_name: str, obj: Object, *, freecad, set_object_property):
    doc = freecad.getDocument(doc_name)
    if not doc:
        freecad.Console.PrintError(f"Document '{doc_name}' not found.\n")
        return f"Document '{doc_name}' not found.\n"

    obj_ins = doc.getObject(obj.name)
    if not obj_ins:
        freecad.Console.PrintError(
            f"Object '{obj.name}' not found in document '{doc_name}'.\n"
        )
        return f"Object '{obj.name}' not found in document '{doc_name}'.\n"

    try:
        # For Fem::ConstraintFixed
        if hasattr(obj_ins, "References") and "References" in obj.properties:
            refs = []
            for ref_name, face in obj.properties["References"]:
                ref_obj = doc.getObject(ref_name)
                if ref_obj:
                    refs.append((ref_obj, face))
                else:
                    raise ValueError(f"Referenced object '{ref_name}' not found.")
            obj_ins.References = refs
            freecad.Console.PrintMessage(
                f"References updated for '{obj.name}' in '{doc_name}'.\n"
            )
            # delete References from properties
            del obj.properties["References"]
        set_object_property(doc, obj_ins, obj.properties)
        doc.recompute()
        freecad.Console.PrintMessage(f"Object '{obj.name}' updated via RPC.\n")
        return True
    except Exception as e:
        return str(e)


def delete_object_gui(doc_name: str, obj_name: str, *, freecad):
    doc = freecad.getDocument(doc_name)
    if not doc:
        freecad.Console.PrintError(f"Document '{doc_name}' not found.\n")
        return f"Document '{doc_name}' not found.\n"

    try:
        doc.removeObject(obj_name)
        doc.recompute()
        freecad.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
        return True
    except Exception as e:
        return str(e)


def get_objects_gui(doc_name, *, freecad, serialize_object):
    doc = freecad.getDocument(doc_name)
    if not doc:
        return []
    results = []
    for obj in doc.Objects:
        try:
            results.append(serialize_object(obj))
        except Exception as e:
            results.append(
                {
                    "Name": getattr(obj, "Name", "<unknown>"),
                    "Label": getattr(obj, "Label", "<unknown>"),
                    "TypeId": getattr(obj, "TypeId", "<unknown>"),
                    "error": f"Serialization failed: {e}",
                }
            )
    return results if results else []


def get_object_gui(doc_name, obj_name, *, freecad, serialize_object):
    doc = freecad.getDocument(doc_name)
    if doc:
        obj = doc.getObject(obj_name)
        if obj:
            try:
                return serialize_object(obj)
            except Exception as e:
                return {"Name": obj_name, "error": str(e)}
    return False


def insert_part_from_library_gui(doc_name, relative_path, *, insert_part_from_library):
    try:
        insert_part_from_library(doc_name, relative_path)
        return True
    except Exception as e:
        return str(e)
