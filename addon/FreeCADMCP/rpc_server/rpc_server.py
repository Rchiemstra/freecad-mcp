import FreeCAD
import FreeCADGui
import ObjectsFem

import contextlib
import ipaddress
import json
import queue
import re
import base64
import io
import os
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Any
from xmlrpc.server import SimpleXMLRPCServer

from PySide import QtCore, QtWidgets

from .parts_library import get_parts_list, insert_part_from_library
from .serialize import serialize_object

rpc_server_thread = None
rpc_server_instance = None


# --- Settings persistence ---

_SETTINGS_FILENAME = "freecad_mcp_settings.json"

_DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
}


def _get_settings_path():
    return os.path.join(FreeCAD.getUserAppDataDir(), _SETTINGS_FILENAME)


def load_settings():
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                settings = json.load(f)
            # Ensure all default keys exist
            for key, value in _DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Failed to load MCP settings: {e}\n")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings):
    path = _get_settings_path()
    try:
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to save MCP settings: {e}\n")


def _set_feature_bool(feature, property_names, value):
    """Set a boolean PartDesign property using version-compatible names."""
    properties = set(getattr(feature, "PropertiesList", []))
    for name in property_names:
        if name in properties:
            setattr(feature, name, bool(value))
            return name
    if value:
        raise AttributeError(
            f"{getattr(feature, 'TypeId', 'Feature')} does not support any of: "
            + ", ".join(property_names)
        )
    return None


def _set_extrusion_symmetric(feature, value):
    """Set symmetric pad/pocket extrusion without touching deprecated Midplane."""
    properties = set(getattr(feature, "PropertiesList", []))
    if "SideType" in properties:
        candidates = ("Two sides", "Symmetric") if value else ("One side",)
        last_error = None
        for candidate in candidates:
            try:
                feature.SideType = candidate
                return "SideType"
            except Exception as err:
                last_error = err
        if last_error:
            raise last_error
    if "Symmetric" in properties:
        feature.Symmetric = bool(value)
        return "Symmetric"
    if "Midplane" in properties:
        if value:
            feature.Midplane = True
            return "Midplane"
        return None
    if value:
        raise AttributeError(
            f"{getattr(feature, 'TypeId', 'Feature')} does not support symmetric extrusion"
        )
    return None


# --- IP-filtered XML-RPC server ---

class FilteredXMLRPCServer(SimpleXMLRPCServer):
    """XML-RPC server that filters connections by allowed IP addresses/subnets."""

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        super().__init__(addr, **kwargs)

    def verify_request(self, request, client_address):
        client_ip = client_address[0]
        try:
            addr = ipaddress.ip_address(client_ip)
            for network in self._allowed_networks:
                if addr in network:
                    return True
        except ValueError:
            pass
        FreeCAD.Console.PrintWarning(
            f"MCP RPC: Rejected connection from {client_ip}\n"
        )
        return False


_COMMA_SEP_RE = re.compile(r"^\s*[^,\s]+(\s*,\s*[^,\s]+)*\s*$")


def validate_allowed_ips(allowed_ips_str):
    """Validate a comma-separated string of IP addresses/subnets.

    Returns a ``(valid, errors)`` tuple.  ``valid`` is a list of normalised
    entry strings that passed validation; ``errors`` is a list of
    human-readable error messages (empty when the input is fully valid).

    Checks performed:
    1. The overall string is well-formed comma-separated (no leading/trailing
       commas, no empty entries between commas, not blank).
    2. Each individual entry is a valid IPv4/IPv6 address or CIDR subnet
       (validated via the stdlib ``ipaddress`` module).
    """
    errors = []

    if not allowed_ips_str or not allowed_ips_str.strip():
        return [], ["Input must not be empty."]

    if not _COMMA_SEP_RE.match(allowed_ips_str):
        return [], [
            "Malformed list — check for leading/trailing commas, "
            "double commas, or missing separators."
        ]

    valid = []
    for entry in allowed_ips_str.split(","):
        entry = entry.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
            valid.append(entry)
        except ValueError:
            errors.append(f"Invalid IP/subnet: '{entry}'")
    return valid, errors


def _parse_allowed_ips(allowed_ips_str):
    """Parse a comma-separated string of IPs/subnets into a list of ip_network objects."""
    valid, errors = validate_allowed_ips(allowed_ips_str)
    for msg in errors:
        FreeCAD.Console.PrintWarning(f"MCP RPC: {msg}, skipping\n")
    return [ipaddress.ip_network(entry, strict=False) for entry in valid]

# GUI task queue
rpc_request_queue = queue.Queue()
rpc_response_queue = queue.Queue()


def process_gui_tasks():
    while not rpc_request_queue.empty():
        task = rpc_request_queue.get()
        res = task()
        if res is not None:
            rpc_response_queue.put(res)
    QtCore.QTimer.singleShot(500, process_gui_tasks)


@dataclass
class Object:
    name: str
    type: str | None = None
    analysis: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


def set_object_property(
    doc: FreeCAD.Document, obj: FreeCAD.DocumentObject, properties: dict[str, Any]
):
    for prop, val in properties.items():
        try:
            if prop in obj.PropertiesList:
                if prop == "Placement" and isinstance(val, dict):
                    if "Base" in val:
                        pos = val["Base"]
                    elif "Position" in val:
                        pos = val["Position"]
                    else:
                        pos = {}
                    rot = val.get("Rotation", {})
                    placement = FreeCAD.Placement(
                        FreeCAD.Vector(
                            pos.get("x", 0),
                            pos.get("y", 0),
                            pos.get("z", 0),
                        ),
                        FreeCAD.Rotation(
                            FreeCAD.Vector(
                                rot.get("Axis", {}).get("x", 0),
                                rot.get("Axis", {}).get("y", 0),
                                rot.get("Axis", {}).get("z", 1),
                            ),
                            rot.get("Angle", 0),
                        ),
                    )
                    setattr(obj, prop, placement)

                elif isinstance(getattr(obj, prop), FreeCAD.Vector) and isinstance(
                    val, dict
                ):
                    vector = FreeCAD.Vector(
                        val.get("x", 0), val.get("y", 0), val.get("z", 0)
                    )
                    setattr(obj, prop, vector)

                elif prop in ["Base", "Tool", "Source", "Profile"] and isinstance(
                    val, str
                ):
                    ref_obj = doc.getObject(val)
                    if ref_obj:
                        setattr(obj, prop, ref_obj)
                    else:
                        raise ValueError(f"Referenced object '{val}' not found.")

                elif prop == "References" and isinstance(val, list):
                    refs = []
                    for ref_name, face in val:
                        ref_obj = doc.getObject(ref_name)
                        if ref_obj:
                            refs.append((ref_obj, face))
                        else:
                            raise ValueError(f"Referenced object '{ref_name}' not found.")
                    setattr(obj, prop, refs)

                else:
                    setattr(obj, prop, val)
            # ShapeColor is a property of the ViewObject
            elif prop == "ShapeColor" and isinstance(val, (list, tuple)):
                setattr(obj.ViewObject, prop, (float(val[0]), float(val[1]), float(val[2]), float(val[3])))

            elif prop == "ViewObject" and isinstance(val, dict):
                for k, v in val.items():
                    if k == "ShapeColor":
                        setattr(obj.ViewObject, k, (float(v[0]), float(v[1]), float(v[2]), float(v[3])))
                    else:
                        setattr(obj.ViewObject, k, v)

            else:
                setattr(obj, prop, val)

        except Exception as e:
            FreeCAD.Console.PrintError(f"Property '{prop}' assignment error: {e}\n")


class FreeCADRPC:
    """RPC server for FreeCAD"""
    TIMEOUT = 30
    EXECUTE_TIMEOUT = 120

    def _get_res(self, timeout=None):
        """Get result from GUI queue; returns an error string on timeout."""
        t = timeout if timeout is not None else self.TIMEOUT
        try:
            return rpc_response_queue.get(timeout=t)
        except queue.Empty:
            return f"Timed out after {t}s waiting for FreeCAD GUI response"

    def ping(self):
        return True

    def create_document(self, name="New_Document"):
        rpc_request_queue.put(lambda: self._create_document_gui(name))
        res = self._get_res()
        if res is True:
            return {"success": True, "document_name": name}
        else:
            return {"success": False, "error": res}

    def create_object(self, doc_name, obj_data: dict[str, Any]):
        obj = Object(
            name=obj_data.get("Name", "New_Object"),
            type=obj_data["Type"],
            analysis=obj_data.get("Analysis", None),
            properties=obj_data.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._create_object_gui(doc_name, obj))
        res = self._get_res()
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def edit_object(self, doc_name: str, obj_name: str, properties: dict[str, Any]) -> dict[str, Any]:
        obj = Object(
            name=obj_name,
            properties=properties.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._edit_object_gui(doc_name, obj))
        res = self._get_res()
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def delete_object(self, doc_name: str, obj_name: str):
        rpc_request_queue.put(lambda: self._delete_object_gui(doc_name, obj_name))
        res = self._get_res()
        if res is True:
            return {"success": True, "object_name": obj_name}
        else:
            return {"success": False, "error": res}

    def execute_code(self, code: str) -> dict[str, Any]:
        output_buffer = io.StringIO()
        def task():
            try:
                with contextlib.redirect_stdout(output_buffer):
                    exec(code, globals())
                FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
                errors = []
                for _doc_name, _doc in FreeCAD.listDocuments().items():
                    for _obj in _doc.Objects:
                        try:
                            _st = list(getattr(_obj, "State", []))
                            if any(s in ("Invalid", "Error") for s in _st):
                                errors.append({
                                    "doc": _doc_name,
                                    "name": _obj.Name,
                                    "label": getattr(_obj, "Label", _obj.Name),
                                    "state": _st,
                                })
                        except Exception:
                            pass
                return {"ok": True, "recompute_errors": errors}
            except Exception as e:
                FreeCAD.Console.PrintError(f"Error executing Python code: {e}\n")
                return {"ok": False, "error": f"Error executing Python code: {e}"}

        rpc_request_queue.put(task)
        res = self._get_res(self.EXECUTE_TIMEOUT)
        if isinstance(res, str):
            return {"success": False, "error": res}
        if res.get("ok"):
            return {
                "success": True,
                "message": "Python code execution scheduled. \nOutput: " + output_buffer.getvalue(),
                "recompute_errors": res["recompute_errors"],
            }
        else:
            return {"success": False, "error": res.get("error", "Unknown error")}

    def get_objects(self, doc_name):
        # Must run in the GUI thread: serialize_object accesses ViewObject
        # and other GUI-backed properties that FreeCAD guards against
        # access from background threads.
        rpc_request_queue.put(lambda: self._get_objects_gui(doc_name))
        res = self._get_res()
        if isinstance(res, list):
            return res
        return []

    def get_object(self, doc_name, obj_name):
        rpc_request_queue.put(lambda: self._get_object_gui(doc_name, obj_name))
        res = self._get_res()
        # False sentinel means "not found"; timeout string → None
        if res is False or isinstance(res, str):
            return None
        return res

    def insert_part_from_library(self, relative_path):
        rpc_request_queue.put(lambda: self._insert_part_from_library(relative_path))
        res = self._get_res()
        if res is True:
            return {"success": True, "message": "Part inserted from library."}
        else:
            return {"success": False, "error": res}

    def list_documents(self):
        return list(FreeCAD.listDocuments().keys())

    def get_parts_list(self):
        return get_parts_list()

    def get_active_screenshot(self, view_name: str | None = "Isometric", width: int | None = None, height: int | None = None, focus_object: str | None = None) -> str:
        """Get a screenshot of the active view.
        
        Returns a base64-encoded string of the screenshot or None if a screenshot
        cannot be captured (e.g., when in TechDraw or Spreadsheet view).
        """
        # First check if the active view supports screenshots
        def check_view_supports_screenshots():
            try:
                active_view = FreeCADGui.ActiveDocument.ActiveView
                if active_view is None:
                    FreeCAD.Console.PrintWarning("No active view available\n")
                    return False
                
                view_type = type(active_view).__name__
                has_save_image = hasattr(active_view, 'saveImage')
                FreeCAD.Console.PrintMessage(f"View type: {view_type}, Has saveImage: {has_save_image}\n")
                return has_save_image
            except Exception as e:
                FreeCAD.Console.PrintError(f"Error checking view capabilities: {e}\n")
                return False
                
        rpc_request_queue.put(check_view_supports_screenshots)
        supports_screenshots = self._get_res()

        if not supports_screenshots:
            FreeCAD.Console.PrintWarning("Current view does not support screenshots\n")
            return None

        # If view supports screenshots, proceed with capture
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        rpc_request_queue.put(
            lambda: self._save_active_screenshot(tmp_path, view_name, width, height, focus_object)
        )
        res = self._get_res()
        if res is True:
            try:
                with open(tmp_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return encoded
        else:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            FreeCAD.Console.PrintWarning(f"Failed to capture screenshot: {res}\n")
            return None

    def sketch_create(self, doc_name: str, sketch_name: str, body_name: str | None = None, attach_to: str | None = None) -> dict:
        rpc_request_queue.put(lambda: self._sketch_create_gui(doc_name, sketch_name, body_name, attach_to))
        res = self._get_res()
        if res is True:
            return {"success": True, "sketch_name": sketch_name}
        return {"success": False, "error": res}

    def sketch_add_geometry(self, doc_name: str, sketch_name: str, geometry: list) -> dict:
        rpc_request_queue.put(lambda: self._sketch_add_geometry_gui(doc_name, sketch_name, geometry))
        res = self._get_res()
        if isinstance(res, list):
            return {"success": True, "indices": res}
        return {"success": False, "error": res}

    def sketch_add_constraint(self, doc_name: str, sketch_name: str, constraints: list) -> dict:
        rpc_request_queue.put(lambda: self._sketch_add_constraint_gui(doc_name, sketch_name, constraints))
        res = self._get_res()
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def pad_feature(self, doc_name: str, sketch_name: str, pad_name: str, length: float, body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False) -> dict:
        rpc_request_queue.put(lambda: self._pad_feature_gui(doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir))
        res = self._get_res()
        if res is True:
            return {"success": True, "pad_name": pad_name}
        return {"success": False, "error": res}

    def pocket_feature(self, doc_name: str, sketch_name: str, pocket_name: str, length: float, body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False) -> dict:
        rpc_request_queue.put(lambda: self._pocket_feature_gui(doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir))
        res = self._get_res()
        if res is True:
            return {"success": True, "pocket_name": pocket_name}
        return {"success": False, "error": res}

    def recompute_document(self, doc_name: str) -> dict:
        rpc_request_queue.put(lambda: self._recompute_document_gui(doc_name))
        res = self._get_res()
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def undo(self, doc_name: str) -> dict:
        rpc_request_queue.put(lambda: self._undo_gui(doc_name))
        res = self._get_res()
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def redo(self, doc_name: str) -> dict:
        rpc_request_queue.put(lambda: self._redo_gui(doc_name))
        res = self._get_res()
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def get_recompute_log(self, doc_name: str) -> list:
        """Return recompute state for every object in a document (read-only)."""
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return [{"error": f"Document '{doc_name}' not found"}]
        results = []
        for obj in doc.Objects:
            try:
                st = list(getattr(obj, "State", []))
                results.append({
                    "name": obj.Name,
                    "label": getattr(obj, "Label", obj.Name),
                    "type_id": getattr(obj, "TypeId", ""),
                    "state": st,
                    "valid": not any(s in ("Invalid", "Error") for s in st),
                })
            except Exception as e:
                results.append({"name": getattr(obj, "Name", "?"), "error": str(e)})
        return results

    def get_sketch_diagnostics(self, doc_name: str, sketch_name: str) -> dict:
        """Return solver diagnostics for a Sketcher sketch (read-only)."""
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return {"error": f"Document '{doc_name}' not found"}
        sk = doc.getObject(sketch_name)
        if not sk:
            return {"error": f"Sketch '{sketch_name}' not found"}
        info = {
            "name": sk.Name,
            "geometry_count": len(sk.Geometry) if hasattr(sk, "Geometry") else 0,
            "constraint_count": len(sk.Constraints) if hasattr(sk, "Constraints") else 0,
            "state": list(getattr(sk, "State", [])),
            "conflicting_constraints": list(getattr(sk, "ConflictingConstraints", [])),
            "redundant_constraints": list(getattr(sk, "RedundantConstraints", [])),
            "malformed_constraints": list(getattr(sk, "MalformedConstraints", [])),
            "solver_message": getattr(sk, "SolverMessage", None),
            "is_closed": None,
        }
        try:
            shape = sk.Shape
            if shape and not shape.isNull():
                info["is_closed"] = shape.isClosed()
        except Exception:
            pass
        return info

    def close_document(self, doc_name: str) -> dict:
        rpc_request_queue.put(lambda: self._close_document_gui(doc_name))
        res = self._get_res()
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def snapshot(self, doc_name: str) -> dict:
        """I7 — save the current document into a ring buffer of the last 5
        snapshots kept on the FreeCAD module (shared with the execute_code
        snapshot tool). Returns {ok, snapshot_id, doc, count}."""
        rpc_request_queue.put(lambda: self._snapshot_gui(doc_name))
        res = self._get_res()
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": res}

    def restore(self, doc_name: str, snapshot_id: str | None = None) -> dict:
        """I7 — restore a snapshot in place (closes the current doc and reopens
        the snapshot file). Latest snapshot when snapshot_id is None. Shares the
        FreeCAD._mcp_snapshots ring buffer with the execute_code restore tool."""
        rpc_request_queue.put(lambda: self._restore_gui(doc_name, snapshot_id))
        res = self._get_res()
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": res}

    def solve_assembly(self, doc_name: str, assembly_name: str) -> dict:
        """I9 — re-solve an Assembly via the real internal solver. Tries
        assembly.solve() (C++), then JointObject.solveIfAllowed, then recompute."""
        rpc_request_queue.put(lambda: self._solve_assembly_gui(doc_name, assembly_name))
        res = self._get_res()
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": res}

    def _get_objects_gui(self, doc_name):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return []
        results = []
        for obj in doc.Objects:
            try:
                results.append(serialize_object(obj))
            except Exception as e:
                results.append({
                    "Name": getattr(obj, "Name", "<unknown>"),
                    "Label": getattr(obj, "Label", "<unknown>"),
                    "TypeId": getattr(obj, "TypeId", "<unknown>"),
                    "error": f"Serialization failed: {e}",
                })
        return results if results else []

    def _get_object_gui(self, doc_name, obj_name):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            obj = doc.getObject(obj_name)
            if obj:
                try:
                    return serialize_object(obj)
                except Exception as e:
                    return {"Name": obj_name, "error": str(e)}
        return False  # sentinel: not None so process_gui_tasks queues it

    def _create_document_gui(self, name):
        doc = FreeCAD.newDocument(name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Document '{name}' created via RPC.\n")
        return True

    def _create_object_gui(self, doc_name, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            try:
                if obj.type == "Fem::FemMeshGmsh" and obj.analysis:
                    from femmesh.gmshtools import GmshTools
                    res = getattr(doc, obj.analysis).addObject(ObjectsFem.makeMeshGmsh(doc, obj.name))[0]
                    if "Part" in obj.properties:
                        target_obj = doc.getObject(obj.properties["Part"])
                        if target_obj:
                            res.Part = target_obj
                        else:
                            raise ValueError(f"Referenced object '{obj.properties['Part']}' not found.")
                        del obj.properties["Part"]
                    else:
                        raise ValueError("'Part' property not found in properties.")

                    for param, value in obj.properties.items():
                        if hasattr(res, param):
                            setattr(res, param, value)
                    doc.recompute()

                    gmsh_tools = GmshTools(res)
                    gmsh_tools.create_mesh()
                    FreeCAD.Console.PrintMessage(
                        f"FEM Mesh '{res.Name}' generated successfully in '{doc_name}'.\n"
                    )
                elif obj.type.startswith("Fem::"):
                    fem_make_methods = {
                        "MaterialCommon": ObjectsFem.makeMaterialSolid,
                        "AnalysisPython": ObjectsFem.makeAnalysis,
                    }
                    obj_type_short = obj.type.split("::")[1]
                    method_name = "make" + obj_type_short
                    make_method = fem_make_methods.get(obj_type_short, getattr(ObjectsFem, method_name, None))

                    if callable(make_method):
                        res = make_method(doc, obj.name)
                        set_object_property(doc, res, obj.properties)
                        FreeCAD.Console.PrintMessage(
                            f"FEM object '{res.Name}' created with '{method_name}'.\n"
                        )
                    else:
                        raise ValueError(f"No creation method '{method_name}' found in ObjectsFem.")
                    if obj.type != "Fem::AnalysisPython" and obj.analysis:
                        getattr(doc, obj.analysis).addObject(res)
                else:
                    res = doc.addObject(obj.type, obj.name)
                    set_object_property(doc, res, obj.properties)
                    FreeCAD.Console.PrintMessage(
                        f"{res.TypeId} '{res.Name}' added to '{doc_name}' via RPC.\n"
                    )
 
                doc.recompute()
                return True
            except Exception as e:
                return str(e)
        else:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

    def _edit_object_gui(self, doc_name: str, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        obj_ins = doc.getObject(obj.name)
        if not obj_ins:
            FreeCAD.Console.PrintError(f"Object '{obj.name}' not found in document '{doc_name}'.\n")
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

    def _delete_object_gui(self, doc_name: str, obj_name: str):
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

    def _insert_part_from_library(self, relative_path):
        try:
            insert_part_from_library(relative_path)
            return True
        except Exception as e:
            return str(e)

    def _save_active_screenshot(self, save_path: str, view_name: str | None = "Isometric", width: int | None = None, height: int | None = None, focus_object: str | None = None):
        try:
            view = FreeCADGui.ActiveDocument.ActiveView
            # Check if the view supports screenshots
            if not hasattr(view, 'saveImage'):
                return "Current view does not support screenshots"
                
            if view_name is not None:
                if view_name == "Isometric":
                    view.viewIsometric()
                elif view_name == "Front":
                    view.viewFront()
                elif view_name == "Top":
                    view.viewTop()
                elif view_name == "Right":
                    view.viewRight()
                elif view_name == "Back":
                    view.viewBack()
                elif view_name == "Left":
                    view.viewLeft()
                elif view_name == "Bottom":
                    view.viewBottom()
                elif view_name == "Dimetric":
                    view.viewDimetric()
                elif view_name == "Trimetric":
                    view.viewTrimetric()
                else:
                    raise ValueError(f"Invalid view name: {view_name}")

            # Focus on specific object or fit all
            if focus_object:
                doc = FreeCAD.ActiveDocument
                obj = doc.getObject(focus_object) if doc else None
                if obj:
                    FreeCADGui.Selection.clearSelection()
                    FreeCADGui.Selection.addSelection(obj)
                    FreeCADGui.SendMsgToActiveView("ViewSelection")
                else:
                    view.fitAll()
            elif view_name is not None:
                view.fitAll()
            FreeCADGui.updateGui()
            if width is not None and height is not None:
                view.saveImage(save_path, width, height)
            else:
                view.saveImage(save_path)
            return True
        except Exception as e:
            return str(e)


    def _sketch_create_gui(self, doc_name, sketch_name, body_name, attach_to):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."

            if body_name:
                body = doc.getObject(body_name)
                if not body:
                    return f"Body '{body_name}' not found."
                sketch = body.newObject("Sketcher::SketchObject", sketch_name)
            else:
                sketch = doc.addObject("Sketcher::SketchObject", sketch_name)

            if attach_to:
                if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
                    plane_obj = None
                    for obj in doc.Objects:
                        if obj.TypeId == "App::Origin":
                            for feat in getattr(obj, "OriginFeatures", []):
                                if feat.Label == attach_to:
                                    plane_obj = feat
                                    break
                        if plane_obj:
                            break
                    if plane_obj:
                        sketch.AttachmentSupport = [(plane_obj, "")]
                        sketch.MapMode = "FlatFace"
                    else:
                        # Fall back to placement rotation
                        if attach_to == "XZ_Plane":
                            sketch.Placement = FreeCAD.Placement(
                                FreeCAD.Vector(0, 0, 0),
                                FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90),
                            )
                        elif attach_to == "YZ_Plane":
                            sketch.Placement = FreeCAD.Placement(
                                FreeCAD.Vector(0, 0, 0),
                                FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90),
                            )
                elif ":" in attach_to:
                    obj_name, face = attach_to.split(":", 1)
                    ref_obj = doc.getObject(obj_name)
                    if not ref_obj:
                        return f"Object '{obj_name}' not found for attach_to."
                    sketch.AttachmentSupport = [(ref_obj, face)]
                    sketch.MapMode = "FlatFace"

            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Sketch '{sketch_name}' created in '{doc_name}'.\n")
            return True
        except Exception as e:
            return str(e)

    def _sketch_add_geometry_gui(self, doc_name, sketch_name, geometry):
        try:
            import math
            import Part
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            indices = []
            for geom in geometry:
                geom_type = geom.get("type", "").lower()
                construction = geom.get("construction", False)

                if geom_type == "line":
                    s, e = geom["start"], geom["end"]
                    seg = Part.LineSegment(
                        FreeCAD.Vector(s.get("x", 0), s.get("y", 0), 0),
                        FreeCAD.Vector(e.get("x", 0), e.get("y", 0), 0),
                    )
                    indices.append(sketch.addGeometry(seg, construction))

                elif geom_type == "circle":
                    c = geom.get("center", {"x": 0, "y": 0})
                    r = geom.get("radius", 1)
                    circle = Part.Circle(
                        FreeCAD.Vector(c.get("x", 0), c.get("y", 0), 0),
                        FreeCAD.Vector(0, 0, 1),
                        r,
                    )
                    indices.append(sketch.addGeometry(circle, construction))

                elif geom_type == "arc":
                    c = geom.get("center", {"x": 0, "y": 0})
                    r = geom.get("radius", 1)
                    start_a = math.radians(geom.get("start_angle", 0))
                    end_a = math.radians(geom.get("end_angle", 90))
                    base_circle = Part.Circle(
                        FreeCAD.Vector(c.get("x", 0), c.get("y", 0), 0),
                        FreeCAD.Vector(0, 0, 1),
                        r,
                    )
                    arc = Part.ArcOfCircle(base_circle, start_a, end_a)
                    indices.append(sketch.addGeometry(arc, construction))

                elif geom_type == "rectangle":
                    x1, y1 = geom.get("x1", 0), geom.get("y1", 0)
                    x2, y2 = geom.get("x2", 10), geom.get("y2", 10)
                    corners = [
                        (FreeCAD.Vector(x1, y1, 0), FreeCAD.Vector(x2, y1, 0)),
                        (FreeCAD.Vector(x2, y1, 0), FreeCAD.Vector(x2, y2, 0)),
                        (FreeCAD.Vector(x2, y2, 0), FreeCAD.Vector(x1, y2, 0)),
                        (FreeCAD.Vector(x1, y2, 0), FreeCAD.Vector(x1, y1, 0)),
                    ]
                    for p1, p2 in corners:
                        idx = sketch.addGeometry(Part.LineSegment(p1, p2), construction)
                        indices.append(idx)

                elif geom_type == "point":
                    pt = Part.Point(FreeCAD.Vector(geom.get("x", 0), geom.get("y", 0), 0))
                    indices.append(sketch.addGeometry(pt, construction))

                else:
                    return f"Unknown geometry type: '{geom_type}'"

            doc.recompute()
            return indices
        except Exception as e:
            return str(e)

    def _sketch_add_constraint_gui(self, doc_name, sketch_name, constraints):
        try:
            import Sketcher
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            for c in constraints:
                t = c.get("type", "")
                if t == "Coincident":
                    sketch.addConstraint(Sketcher.Constraint("Coincident", c["geo1"], c["pos1"], c["geo2"], c["pos2"]))
                elif t == "Horizontal":
                    sketch.addConstraint(Sketcher.Constraint("Horizontal", c["geo"]))
                elif t == "Vertical":
                    sketch.addConstraint(Sketcher.Constraint("Vertical", c["geo"]))
                elif t == "Distance":
                    if "geo2" in c:
                        sketch.addConstraint(Sketcher.Constraint("Distance", c["geo1"], c.get("pos1", 0), c["geo2"], c.get("pos2", 0), c["value"]))
                    elif "pos" in c:
                        sketch.addConstraint(Sketcher.Constraint("Distance", c["geo"], c["pos"], c["value"]))
                    else:
                        sketch.addConstraint(Sketcher.Constraint("Distance", c["geo"], c["value"]))
                elif t == "DistanceX":
                    if "pos" in c:
                        sketch.addConstraint(Sketcher.Constraint("DistanceX", c["geo"], c["pos"], c["value"]))
                    else:
                        sketch.addConstraint(Sketcher.Constraint("DistanceX", c["geo"], c["value"]))
                elif t == "DistanceY":
                    if "pos" in c:
                        sketch.addConstraint(Sketcher.Constraint("DistanceY", c["geo"], c["pos"], c["value"]))
                    else:
                        sketch.addConstraint(Sketcher.Constraint("DistanceY", c["geo"], c["value"]))
                elif t == "Radius":
                    sketch.addConstraint(Sketcher.Constraint("Radius", c["geo"], c["value"]))
                elif t == "Diameter":
                    sketch.addConstraint(Sketcher.Constraint("Diameter", c["geo"], c["value"]))
                elif t == "Angle":
                    if "geo2" in c:
                        sketch.addConstraint(Sketcher.Constraint("Angle", c["geo1"], c.get("pos1", 0), c["geo2"], c.get("pos2", 0), c["value"]))
                    else:
                        sketch.addConstraint(Sketcher.Constraint("Angle", c["geo"], c["value"]))
                elif t == "Parallel":
                    sketch.addConstraint(Sketcher.Constraint("Parallel", c["geo1"], c["geo2"]))
                elif t == "Perpendicular":
                    sketch.addConstraint(Sketcher.Constraint("Perpendicular", c["geo1"], c["geo2"]))
                elif t == "Equal":
                    sketch.addConstraint(Sketcher.Constraint("Equal", c["geo1"], c["geo2"]))
                elif t == "Symmetric":
                    sketch.addConstraint(Sketcher.Constraint("Symmetric", c["geo1"], c["pos1"], c["geo2"], c["pos2"], c["geo3"], c.get("pos3", 0)))
                elif t == "PointOnObject":
                    sketch.addConstraint(Sketcher.Constraint("PointOnObject", c["geo1"], c["pos1"], c["geo2"]))
                elif t == "Tangent":
                    sketch.addConstraint(Sketcher.Constraint("Tangent", c["geo1"], c["geo2"]))
                elif t == "Block":
                    sketch.addConstraint(Sketcher.Constraint("Block", c["geo"]))
                else:
                    return f"Unknown constraint type: '{t}'"

            doc.recompute()
            return True
        except Exception as e:
            return str(e)

    def _pad_feature_gui(self, doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            body = doc.getObject(body_name) if body_name else None
            if not body:
                for obj in doc.Objects:
                    if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                        body = obj
                        break

            if body:
                pad = body.newObject("PartDesign::Pad", pad_name)
            else:
                pad = doc.addObject("PartDesign::Pad", pad_name)

            pad.Profile = (sketch, [""])
            pad.Length = length
            _set_extrusion_symmetric(pad, symmetric)
            _set_feature_bool(pad, ("Reversed",), reversed_dir)
            sketch.Visibility = False
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Pad '{pad_name}' created in '{doc_name}'.\n")
            return True
        except Exception as e:
            return str(e)

    def _pocket_feature_gui(self, doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            body = doc.getObject(body_name) if body_name else None
            if not body:
                for obj in doc.Objects:
                    if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                        body = obj
                        break

            if body:
                pocket = body.newObject("PartDesign::Pocket", pocket_name)
            else:
                pocket = doc.addObject("PartDesign::Pocket", pocket_name)

            pocket.Profile = (sketch, [""])
            pocket.Length = length
            _set_extrusion_symmetric(pocket, symmetric)
            _set_feature_bool(pocket, ("Reversed",), reversed_dir)
            sketch.Visibility = False
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Pocket '{pocket_name}' created in '{doc_name}'.\n")
            return True
        except Exception as e:
            return str(e)

    def _recompute_document_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            doc.recompute()
            return True
        except Exception as e:
            return str(e)

    def _undo_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            doc.undo()
            return True
        except Exception as e:
            return str(e)

    def _redo_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            doc.redo()
            return True
        except Exception as e:
            return str(e)

    def _close_document_gui(self, doc_name: str):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            FreeCAD.closeDocument(doc_name)
            FreeCAD.Console.PrintMessage(f"Document '{doc_name}' closed via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _snapshot_gui(self, doc_name: str):
        import os
        import tempfile
        import time
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            if not hasattr(FreeCAD, "_mcp_snapshots"):
                FreeCAD._mcp_snapshots = []
            fd, path = tempfile.mkstemp(suffix=".FCStd", prefix="mcp_snap_")
            os.close(fd)
            try:
                doc.save(path)
            except Exception as e:
                try:
                    os.remove(path)
                except Exception:
                    pass
                return {"ok": False, "error": f"Failed to save snapshot: {e}"}
            sid = "snap-" + str(int(time.time() * 1000))
            FreeCAD._mcp_snapshots.append(
                {"id": sid, "path": path, "doc": doc.Name, "t": time.time()}
            )
            while len(FreeCAD._mcp_snapshots) > 5:
                old = FreeCAD._mcp_snapshots.pop(0)
                try:
                    os.remove(old["path"])
                except Exception:
                    pass
            return {"ok": True, "snapshot_id": sid, "doc": doc.Name,
                    "count": len(FreeCAD._mcp_snapshots)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _restore_gui(self, doc_name: str, snapshot_id):
        import os
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            snaps = getattr(FreeCAD, "_mcp_snapshots", [])
            if not snaps:
                return {"ok": False, "error": "No snapshots available to restore"}
            target = None
            if snapshot_id:
                for s in snaps:
                    if s["id"] == snapshot_id:
                        target = s
                        break
                if target is None:
                    return {"ok": False, "error": f"Snapshot not found: {snapshot_id}"}
            else:
                target = snaps[-1]
            if not os.path.exists(target["path"]):
                return {"ok": False, "error": f"Snapshot file missing: {target['path']}"}
            cur = doc.Name
            try:
                FreeCAD.closeDocument(cur)
            except Exception:
                pass
            restored = FreeCAD.open(target["path"])
            return {"ok": True, "restored_id": target["id"], "doc": cur,
                    "new_doc": restored.Name if restored is not None else cur,
                    "count": len(snaps)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _solve_assembly_gui(self, doc_name: str, assembly_name: str):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            asm = doc.getObject(assembly_name)
            if not asm:
                return {"ok": False, "error": f"Assembly '{assembly_name}' not found."}
            try:
                is_asm = asm.isDerivedFrom("Assembly::AssemblyObject")
            except Exception:
                is_asm = False
            if not is_asm:
                return {"ok": False, "error": f"Object '{assembly_name}' is not an Assembly::AssemblyObject."}
            method = None
            status = None
            error = None
            try:
                if hasattr(asm, "solve"):
                    status = asm.solve()
                    method = "assembly.solve()"
            except Exception as e:
                error = str(e)
            if method is None:
                try:
                    import JointObject
                    JointObject.solveIfAllowed(asm, True)
                    method = "JointObject.solveIfAllowed"
                    status = "ok"
                except Exception as e:
                    error = (str(e) if error is None else error + " | " + str(e))
            if method is None:
                try:
                    asm.Document.recompute()
                    method = "recompute"
                    status = "ok"
                except Exception as e:
                    return {"ok": False, "error": f"solve_assembly failed: {error} | {e}"}
            try:
                doc.recompute()
            except Exception:
                pass
            return {"ok": True, "assembly": asm.Name, "method": method,
                    "status": str(status) if status is not None else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def start_rpc_server(port=9875):
    global rpc_server_thread, rpc_server_instance

    if rpc_server_instance:
        return "RPC Server already running."

    settings = load_settings()
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")

    if remote_enabled:
        host = "0.0.0.0"
    else:
        host = "localhost"

    rpc_server_instance = FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    rpc_server_instance.register_instance(FreeCADRPC())

    def server_loop():
        FreeCAD.Console.PrintMessage(f"RPC Server started at {host}:{port}\n")
        if remote_enabled:
            FreeCAD.Console.PrintMessage(f"Remote connections enabled. Allowed IPs: {allowed_ips}\n")
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    QtCore.QTimer.singleShot(500, process_gui_tasks)

    msg = f"RPC Server started at {host}:{port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    return msg


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread

    if rpc_server_instance:
        rpc_server_instance.shutdown()
        rpc_server_thread.join()
        rpc_server_instance = None
        rpc_server_thread = None
        FreeCAD.Console.PrintMessage("RPC Server stopped.\n")
        return "RPC Server stopped."

    return "RPC Server was not running."


class StartRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": "Start RPC Server"}

    def Activated(self):
        msg = start_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class StopRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Stop RPC Server", "ToolTip": "Stop RPC Server"}

    def Activated(self):
        msg = stop_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class ToggleRemoteConnectionsCommand:
    def GetResources(self):
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = load_settings()
        settings["remote_enabled"] = bool(checked)
        save_settings(settings)

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            FreeCAD.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
        else:
            FreeCAD.Console.PrintMessage("Remote connections disabled.\n")

        if rpc_server_instance:
            FreeCAD.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

    def IsActive(self):
        return True


class ConfigureAllowedIPsCommand:
    def GetResources(self):
        return {
            "MenuText": "Configure Allowed IPs",
            "ToolTip": "Set which IP addresses or subnets are allowed to connect to the RPC server.",
        }

    def Activated(self):
        settings = load_settings()
        current_ips = settings.get("allowed_ips", "127.0.0.1")
        text, ok = QtWidgets.QInputDialog.getText(
            None,
            "Allowed IP Addresses",
            "Enter allowed IP addresses or subnets (comma-separated):\n"
            "Examples: 127.0.0.1, 192.168.1.0/24, 10.0.0.5",
            QtWidgets.QLineEdit.Normal,
            current_ips,
        )
        if ok and text.strip():
            valid, errors = validate_allowed_ips(text.strip())
            if errors:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Invalid IP Configuration",
                    "The following errors were found:\n\n"
                    + "\n".join(f"• {e}" for e in errors)
                    + ("\n\nOnly valid entries will be saved."
                       if valid else "\n\nNo valid entries found. Settings not changed."),
                )
            if not valid:
                FreeCAD.Console.PrintWarning("Allowed IPs not changed — no valid entries.\n")
                return
            normalised = ", ".join(valid)
            settings["allowed_ips"] = normalised
            save_settings(settings)
            FreeCAD.Console.PrintMessage(
                f"Allowed IPs updated to: {normalised}\n"
            )
            if rpc_server_instance:
                FreeCAD.Console.PrintMessage(
                    "Restart the RPC server for changes to take effect.\n"
                )
        else:
            FreeCAD.Console.PrintMessage("Allowed IPs not changed.\n")

    def IsActive(self):
        return True


class ToggleAutoStartCommand:
    def GetResources(self):
        return {
            "MenuText": "Auto-Start Server",
            "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = load_settings()
        settings["auto_start_rpc"] = bool(checked)
        save_settings(settings)

        if settings["auto_start_rpc"]:
            FreeCAD.Console.PrintMessage(
                "MCP RPC server will start automatically on next FreeCAD launch.\n"
            )
        else:
            FreeCAD.Console.PrintMessage(
                "MCP RPC server auto-start disabled.\n"
            )

    def IsActive(self):
        return True


FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand())
FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand())
FreeCADGui.addCommand("Toggle_Auto_Start", ToggleAutoStartCommand())
FreeCADGui.addCommand("Toggle_Remote_Connections", ToggleRemoteConnectionsCommand())
FreeCADGui.addCommand("Configure_Allowed_IPs", ConfigureAllowedIPsCommand())


def _sync_toggle_states():
    """Sync checkable menu items with saved settings on startup."""
    try:
        settings = load_settings()
        main_window = FreeCADGui.getMainWindow()
        toggle_map = {
            "Remote Connections": settings.get("remote_enabled", False),
            "Auto-Start Server": settings.get("auto_start_rpc", False),
        }
        found = 0
        for action in main_window.findChildren(QtWidgets.QAction):
            if action.text() in toggle_map:
                action.setChecked(toggle_map[action.text()])
                found += 1
                if found == len(toggle_map):
                    return
    except Exception:
        pass
    # Retry if menu not ready yet
    QtCore.QTimer.singleShot(2000, _sync_toggle_states)


QtCore.QTimer.singleShot(2000, _sync_toggle_states)
