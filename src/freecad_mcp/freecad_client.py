import logging
import xmlrpc.client
from typing import Any

from .execute_options import ExecuteOptions
from .template_resources import read_template_text


logger = logging.getLogger("FreeCADMCPserver")

_SCREENSHOT_SUPPORT_CHECK = read_template_text("freecad_client/screenshot_support_check.py.txt")


class FreeCADConnection:
    def __init__(self, host: str = "localhost", port: int = 9875):
        self.server = xmlrpc.client.ServerProxy(f"http://{host}:{port}", allow_none=True)

    def disconnect(self) -> None:
        # Transport.close() clears cached HTTP connections if one was opened.
        transport = getattr(self.server, "_ServerProxy__transport", None)
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    def ping(self) -> bool:
        return self.server.ping()

    def create_document(self, name: str) -> dict[str, Any]:
        return self.server.create_document(name)

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.create_object(doc_name, obj_data)

    def edit_object(self, doc_name: str, obj_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.edit_object(doc_name, obj_name, obj_data)

    def delete_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.delete_object(doc_name, obj_name)

    def insert_part_from_library(self, relative_path: str) -> dict[str, Any]:
        return self.server.insert_part_from_library(relative_path)

    def execute_code(
        self,
        code: str,
        options: dict[str, Any] | ExecuteOptions | None = None,
    ) -> dict[str, Any]:
        opts = options.to_dict() if isinstance(options, ExecuteOptions) else (options or {})
        return self.server.execute_code(code, opts)

    def get_active_screenshot(
        self,
        view_name: str | None = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
    ) -> str | None:
        try:
            result = self.server.execute_code(_SCREENSHOT_SUPPORT_CHECK)
            if not result.get("success", False) or "Current view does not support screenshots" in result.get("message", ""):
                logger.info("Screenshot unavailable in current view (likely Spreadsheet or TechDraw view)")
                return None

            return self.server.get_active_screenshot(view_name, width, height, focus_object)
        except Exception as e:
            logger.error(f"Error getting screenshot: {e}")
            return None

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()

    def list_documents(self) -> list[str]:
        return self.server.list_documents()

    def sketch_create(self, doc_name: str, sketch_name: str, body_name: str | None = None, attach_to: str | None = None) -> dict[str, Any]:
        return self.server.sketch_create(doc_name, sketch_name, body_name, attach_to)

    def sketch_add_geometry(self, doc_name: str, sketch_name: str, geometry: list) -> dict[str, Any]:
        return self.server.sketch_add_geometry(doc_name, sketch_name, geometry)

    def sketch_add_constraint(self, doc_name: str, sketch_name: str, constraints: list) -> dict[str, Any]:
        return self.server.sketch_add_constraint(doc_name, sketch_name, constraints)

    def pad_feature(self, doc_name: str, sketch_name: str, pad_name: str, length: float, body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False) -> dict[str, Any]:
        return self.server.pad_feature(doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir)

    def pocket_feature(self, doc_name: str, sketch_name: str, pocket_name: str, length: float, body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False) -> dict[str, Any]:
        return self.server.pocket_feature(doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir)

    def recompute_document(self, doc_name: str) -> dict[str, Any]:
        return self.server.recompute_document(doc_name)

    def undo(self, doc_name: str) -> dict[str, Any]:
        return self.server.undo(doc_name)

    def redo(self, doc_name: str) -> dict[str, Any]:
        return self.server.redo(doc_name)
