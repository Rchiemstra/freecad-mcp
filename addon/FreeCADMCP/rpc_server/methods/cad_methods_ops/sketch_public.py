"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from .features_gui import body_create_gui, body_set_tip_gui, pad_feature_gui, pocket_feature_gui
from .sketch_gui_constraints import (
    sketch_add_constraint_gui,
    sketch_delete_constraint_gui,
    sketch_edit_constraint_gui,
)
from .sketch_gui_create import sketch_attach_gui, sketch_create_gui
from .sketch_gui_geometry import sketch_add_geometry_gui, sketch_delete_geometry_gui


def sketch_create(
    self,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_create_gui(doc_name, sketch_name, body_name, attach_to)
    )
    return self._adapt_gui_mutation_result(
        res, success_fields={"sketch_name": sketch_name}
    )


def sketch_add_geometry(
    self, doc_name: str, sketch_name: str, geometry: list
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_add_geometry_gui(doc_name, sketch_name, geometry)
    )
    return self._adapt_gui_mutation_result(
        res,
        result_field="indices",
        expected_result_type=list,
    )


def sketch_add_constraint(
    self, doc_name: str, sketch_name: str, constraints: list
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_add_constraint_gui(doc_name, sketch_name, constraints)
    )
    return self._adapt_gui_mutation_result(res)


def sketch_delete_constraint(
    self,
    doc_name: str,
    sketch_name: str,
    constraint_indices=None,
    constraint_names=None,
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_delete_constraint_gui(
            doc_name,
            sketch_name,
            constraint_indices,
            constraint_names,
        )
    )
    return self._adapt_gui_mutation_result(res)


def sketch_delete_geometry(
    self,
    doc_name: str,
    sketch_name: str,
    geometry_indices: list,
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_delete_geometry_gui(
            doc_name,
            sketch_name,
            geometry_indices,
        )
    )
    return self._adapt_gui_mutation_result(res)


def sketch_attach(
    self, doc_name: str, sketch_name: str, support, attachment_offset=None
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_attach_gui(
            doc_name, sketch_name, support, attachment_offset
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def sketch_edit_constraint(
    self,
    doc_name: str,
    sketch_name: str,
    value=None,
    name=None,
    index=None,
) -> dict:
    res = self._dispatch_gui(
        lambda: sketch_edit_constraint_gui(
            doc_name, sketch_name, value, name, index
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def pad_feature(
    self,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> dict:
    res = self._dispatch_gui(
        lambda: pad_feature_gui(
            doc_name,
            sketch_name,
            pad_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
        )
    )
    return self._adapt_gui_mutation_result(
        res, success_fields={"pad_name": pad_name}
    )


def pocket_feature(
    self,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> dict:
    res = self._dispatch_gui(
        lambda: pocket_feature_gui(
            doc_name,
            sketch_name,
            pocket_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
        )
    )
    return self._adapt_gui_mutation_result(
        res, success_fields={"pocket_name": pocket_name}
    )


def body_create(self, doc_name: str, body_name: str) -> dict:
    res = self._dispatch_gui(lambda: body_create_gui(doc_name, body_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


def body_set_tip(self, doc_name: str, body_name: str, feature_name: str) -> dict:
    res = self._dispatch_gui(
        lambda: body_set_tip_gui(doc_name, body_name, feature_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}
