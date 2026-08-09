"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from .cad_mutation import run_cad_mutation
from .features_gui import (
    body_create_gui,
    body_set_tip_gui,
    pad_feature_gui,
    pocket_feature_gui,
)
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
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_create_gui(
                doc_name,
                sketch_name,
                body_name,
                attach_to,
                freecad=collaborators.freecad,
            ),
            structural=True,
        )
    )
    return self._adapt_gui_mutation_result(
        res, success_fields={"sketch_name": sketch_name}
    )


def sketch_add_geometry(self, doc_name: str, sketch_name: str, geometry: list) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_add_geometry_gui(
                doc_name,
                sketch_name,
                geometry,
                freecad=collaborators.freecad,
                part=collaborators.part,
            ),
        )
    )
    return self._adapt_gui_mutation_result(
        res,
        result_field="indices",
        expected_result_type=list,
    )


def sketch_add_constraint(
    self, doc_name: str, sketch_name: str, constraints: list
) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_add_constraint_gui(
                doc_name,
                sketch_name,
                constraints,
                freecad=collaborators.freecad,
                sketcher=collaborators.sketcher,
            ),
        )
    )
    return self._adapt_gui_mutation_result(res)


def sketch_delete_constraint(
    self,
    doc_name: str,
    sketch_name: str,
    constraint_indices=None,
    constraint_names=None,
) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_delete_constraint_gui(
                doc_name,
                sketch_name,
                constraint_indices,
                constraint_names,
                freecad=collaborators.freecad,
            ),
        )
    )
    return self._adapt_gui_mutation_result(res)


def sketch_delete_geometry(
    self,
    doc_name: str,
    sketch_name: str,
    geometry_indices: list,
) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_delete_geometry_gui(
                doc_name,
                sketch_name,
                geometry_indices,
                freecad=collaborators.freecad,
            ),
        )
    )
    return self._adapt_gui_mutation_result(res)


def sketch_attach(
    self, doc_name: str, sketch_name: str, support, attachment_offset=None
) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_attach_gui(
                doc_name,
                sketch_name,
                support,
                attachment_offset,
                freecad=collaborators.freecad,
                dict_to_placement=collaborators.dict_to_placement,
                placement_to_dict=collaborators.placement_to_dict,
            ),
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
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: sketch_edit_constraint_gui(
                doc_name, sketch_name, value, name, index, freecad=collaborators.freecad
            ),
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def _run_structural_feature(collaborators, doc_name, create_feature):
    deferred_presentation = None

    def create_model():
        nonlocal deferred_presentation
        result = create_feature()
        apply_after_commit = getattr(result, "apply_after_commit", None)
        if callable(apply_after_commit):
            deferred_presentation = apply_after_commit
            return True
        return result

    result = run_cad_mutation(
        collaborators,
        doc_name,
        create_model,
        structural=True,
    )
    if result is True and deferred_presentation is not None:
        try:
            deferred_presentation()
        except Exception as exc:
            return str(exc)
    return result


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
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: _run_structural_feature(
            collaborators,
            doc_name,
            lambda: pad_feature_gui(
                doc_name,
                sketch_name,
                pad_name,
                length,
                body_name,
                symmetric,
                reversed_dir,
                freecad=collaborators.freecad,
                set_extrusion_symmetric=collaborators.set_extrusion_symmetric,
                set_feature_bool=collaborators.set_feature_bool,
            ),
        )
    )
    return self._adapt_gui_mutation_result(res, success_fields={"pad_name": pad_name})


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
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: _run_structural_feature(
            collaborators,
            doc_name,
            lambda: pocket_feature_gui(
                doc_name,
                sketch_name,
                pocket_name,
                length,
                body_name,
                symmetric,
                reversed_dir,
                freecad=collaborators.freecad,
                set_extrusion_symmetric=collaborators.set_extrusion_symmetric,
                set_feature_bool=collaborators.set_feature_bool,
            ),
        )
    )
    return self._adapt_gui_mutation_result(
        res, success_fields={"pocket_name": pocket_name}
    )


def body_create(self, doc_name: str, body_name: str) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: body_create_gui(doc_name, body_name, freecad=collaborators.freecad),
            structural=True,
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def body_set_tip(self, doc_name: str, body_name: str, feature_name: str) -> dict:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            lambda: body_set_tip_gui(
                doc_name, body_name, feature_name, freecad=collaborators.freecad
            ),
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}
