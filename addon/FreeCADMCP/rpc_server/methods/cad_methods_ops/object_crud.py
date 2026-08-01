"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

import FreeCAD

from ...parts_library import insert_part_from_library as insert_part_from_library_impl
from ...property_mapper import Object, set_object_property
from ...serialize import serialize_object


def create_object(self, doc_name, obj_data: dict[str, Any]):
    from ...object_factory import create_object_gui

    obj = Object(
        name=obj_data.get("Name", "New_Object"),
        type=obj_data["Type"],
        analysis=obj_data.get("Analysis"),
        properties=obj_data.get("Properties", {}),
    )
    res = self._dispatch_gui(lambda: create_object_gui(doc_name, obj))
    return self._adapt_gui_mutation_result(
        res, success_fields={"object_name": obj.name}
    )


def edit_object(
    self, doc_name: str, obj_name: str, properties: dict[str, Any]
) -> dict[str, Any]:
    obj = Object(
        name=obj_name,
        properties=properties.get("Properties", {}),
    )
    res = self._dispatch_gui(lambda: edit_object_gui(doc_name, obj))
    return self._adapt_gui_mutation_result(
        res, success_fields={"object_name": obj.name}
    )


def delete_object(self, doc_name: str, obj_name: str):
    res = self._dispatch_gui(lambda: delete_object_gui(doc_name, obj_name))
    return self._adapt_gui_mutation_result(
        res, success_fields={"object_name": obj_name}
    )


def get_objects(self, doc_name):
    # Must run in the GUI thread: serialize_object accesses ViewObject
    # and other GUI-backed properties that FreeCAD guards against
    # access from background threads.
    res = self._dispatch_gui(lambda: get_objects_gui(doc_name))
    if isinstance(res, list):
        return res
    return []


def get_object(self, doc_name, obj_name):
    res = self._dispatch_gui(lambda: get_object_gui(doc_name, obj_name))
    # False sentinel means "not found"; timeout string → None
    if res is False or isinstance(res, str):
        return None
    return res


def insert_part_from_library(self, doc_name, relative_path):
    def insert_part_task():
        return insert_part_from_library_gui(doc_name, relative_path)

    res = self._dispatch_gui(insert_part_task)
    return self._adapt_gui_mutation_result(
        res,
        success_fields={"message": "Part inserted from library."},
    )


def edit_object_gui(doc_name: str, obj: Object):
    doc = FreeCAD.getDocument(doc_name)
    if not doc:
        FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
        return f"Document '{doc_name}' not found.\n"

    obj_ins = doc.getObject(obj.name)
    if not obj_ins:
        FreeCAD.Console.PrintError(
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
            FreeCAD.Console.PrintMessage(
                f"References updated for '{obj.name}' in '{doc_name}'.\n"
            )
            # delete References from properties
            del obj.properties["References"]
        set_object_property(doc, obj_ins, obj.properties)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Object '{obj.name}' updated via RPC.\n")
        return True
    except Exception as e:
        return str(e)


def delete_object_gui(doc_name: str, obj_name: str):
    doc = FreeCAD.getDocument(doc_name)
    if not doc:
        FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
        return f"Document '{doc_name}' not found.\n"

    try:
        doc.removeObject(obj_name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
        return True
    except Exception as e:
        return str(e)


def get_objects_gui(doc_name):
    doc = FreeCAD.getDocument(doc_name)
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


def get_object_gui(doc_name, obj_name):
    doc = FreeCAD.getDocument(doc_name)
    if doc:
        obj = doc.getObject(obj_name)
        if obj:
            try:
                return serialize_object(obj)
            except Exception as e:
                return {"Name": obj_name, "error": str(e)}
    return False


def insert_part_from_library_gui(doc_name, relative_path):
    try:
        insert_part_from_library_impl(doc_name, relative_path)
        return True
    except Exception as e:
        return str(e)
