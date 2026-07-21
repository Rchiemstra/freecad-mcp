import logging
import xmlrpc.client
from typing import Any

from .execute_options import ExecuteOptions
from .template_resources import read_template_text


logger = logging.getLogger("FreeCADMCPserver")

_SCREENSHOT_SUPPORT_CHECK = read_template_text("freecad_client/screenshot_support_check.py.txt")


class _TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport with a configurable socket timeout.

    The default Transport has no timeout, so a frozen FreeCAD GUI thread
    causes the MCP client to hang indefinitely (observed: 4+ minute waits).
    """
    def __init__(self, timeout: float = 30, **kwargs):
        super().__init__(**kwargs)
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class FreeCADConnection:
    def __init__(self, host: str = "localhost", port: int = 9875, timeout: float = 150):
        self._uri = f"http://{host}:{port}"
        self._timeout = timeout
        self.server = self._make_proxy(timeout)

    def _make_proxy(self, timeout: float) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(
            self._uri,
            allow_none=True,
            transport=_TimeoutTransport(timeout=timeout),
        )

    def disconnect(self) -> None:
        # Transport.close() clears cached HTTP connections if one was opened.
        transport = getattr(self.server, "_ServerProxy__transport", None)
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    def ping(self) -> bool:
        return self.server.ping()

    def check_rpc_sync(self, nonce: str) -> dict[str, Any]:
        return self.server.check_rpc_sync(nonce)

    def create_document(self, name: str) -> dict[str, Any]:
        return self.server.create_document(name)

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.create_object(doc_name, obj_data)

    def edit_object(self, doc_name: str, obj_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.edit_object(doc_name, obj_name, obj_data)

    def inspect_references(
        self,
        doc_name: str,
        object_names: list[str] | None = None,
        only_invalid: bool = False,
        validate: bool = False,
    ) -> dict[str, Any]:
        return self.server.inspect_references(
            doc_name, object_names, only_invalid, validate
        )

    def repair_references(
        self,
        doc_name: str,
        repairs: list[dict[str, Any]],
        recompute: bool = False,
        validate: bool = False,
    ) -> dict[str, Any]:
        return self.server.repair_references(doc_name, repairs, recompute, validate)

    def delete_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.delete_object(doc_name, obj_name)


    def reload_document(self, doc_name: str) -> dict[str, Any]:
        return self.server.reload_document(doc_name)

    def insert_part_from_library(self, relative_path: str) -> dict[str, Any]:
        return self.server.insert_part_from_library(relative_path)

    def execute_code(
        self,
        code: str,
        options: dict[str, Any] | ExecuteOptions | None = None,
    ) -> dict[str, Any]:
        opts = options.to_dict() if isinstance(options, ExecuteOptions) else (options or {})
        return self.server.execute_code(code, opts)

    def get_worker_status(self) -> dict[str, Any]:
        return self.server.get_worker_status()

    def cancel_worker_job(self, job_id: str) -> dict[str, Any]:
        return self.server.cancel_worker_job(job_id)

    def execute_code_async(self, code: str) -> dict[str, Any]:
        return self.server.execute_code_async(code)

    def get_active_screenshot(
        self,
        view_name: str | None = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
        focus_objects: list[str] | None = None,
        yaw_deg: float | None = None,
    ) -> str | None:
        try:
            return self.server.get_active_screenshot(
                view_name,
                width,
                height,
                focus_object,
                focus_objects,
                yaw_deg,
            )
        except Exception as e:
            logger.error(f"Error getting screenshot: {e}")
            return None

    def capture_view_sequence(
        self,
        frames: list[dict[str, Any]] | None = None,
        width: int | None = None,
        height: int | None = None,
        orbit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.capture_view_sequence(frames, width, height, orbit)
        except Exception as e:
            logger.error(f"Error capturing view sequence: {e}")
            return {"ok": False, "error": str(e), "frames": []}

    def capture_view_sequence_to_disk(
        self,
        frames: list[dict[str, Any]] | None = None,
        width: int | None = None,
        height: int | None = None,
        orbit: dict[str, Any] | None = None,
        frame_dir: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.capture_view_sequence_to_disk(
                frames, width, height, orbit, frame_dir
            )
        except Exception as e:
            logger.error(f"Error capturing view sequence to disk: {e}")
            return {"ok": False, "error": str(e), "frame_paths": []}

    def refresh_view(
        self,
        focus_objects: list[str] | None = None,
        focus_object: str | None = None,
        touch_objects: list[str] | None = None,
        fit: bool = False,
        capture: bool = False,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.refresh_view(
                focus_objects,
                focus_object,
                touch_objects,
                fit,
                capture,
                view_name,
                width,
                height,
            )
        except Exception as e:
            logger.error(f"Error refreshing view: {e}")
            return {"ok": False, "error": str(e)}

    def animate_placement(
        self,
        doc_name: str,
        obj_name: str,
        keyframes: list[dict[str, Any]] | None = None,
        path_object: str | None = None,
        sample_count: int = 12,
        view_name: str = "Isometric",
        focus_objects: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self.server.animate_placement(
                doc_name,
                obj_name,
                keyframes,
                path_object,
                sample_count,
                view_name,
                focus_objects,
                width,
                height,
            )
        except Exception as e:
            logger.error(f"Error animating placement: {e}")
            return {"ok": False, "error": str(e)}

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()

    def list_documents(self) -> list[str]:
        return self.server.list_documents()

    def open_document(self, path: str) -> dict[str, Any]:
        return self.server.open_document(path)

    def activate_document(self, doc_name: str) -> dict[str, Any]:
        return self.server.activate_document(doc_name)

    def set_tree_expanded(
        self,
        doc_name: str,
        object_names: list[str] | None = None,
        mode: str = "expand",
    ) -> dict[str, Any]:
        return self.server.set_tree_expanded(doc_name, object_names, mode)

    def select_subshapes(
        self,
        doc_name: str,
        selections: list | None = None,
        clear: bool = True,
    ) -> dict[str, Any]:
        return self.server.select_subshapes(doc_name, selections, clear)

    def get_selection(self) -> dict[str, Any]:
        return self.server.get_selection()

    def set_section_view(
        self,
        enabled: bool | None = None,
        placement: dict[str, Any] | None = None,
        base: list[float] | None = None,
        normal: list[float] | None = None,
        no_manip: bool = True,
    ) -> dict[str, Any]:
        return self.server.set_section_view(
            enabled, placement, base, normal, no_manip
        )

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

    def spreadsheet_create(self, doc_name: str, sheet_name: str) -> dict[str, Any]:
        return self.server.spreadsheet_create(doc_name, sheet_name)

    def spreadsheet_set_cells(self, doc_name: str, sheet_name: str, cells: list) -> dict[str, Any]:
        return self.server.spreadsheet_set_cells(doc_name, sheet_name, cells)

    def spreadsheet_get_cells(self, doc_name: str, sheet_name: str, addresses: list) -> dict[str, Any]:
        return self.server.spreadsheet_get_cells(doc_name, sheet_name, addresses)

    def spreadsheet_set_alias(self, doc_name: str, sheet_name: str, address: str, alias: str) -> dict[str, Any]:
        return self.server.spreadsheet_set_alias(doc_name, sheet_name, address, alias)

    def spreadsheet_list_aliases(self, doc_name: str, sheet_name: str) -> dict[str, Any]:
        return self.server.spreadsheet_list_aliases(doc_name, sheet_name)

    def set_expression(self, doc_name: str, object_name: str, prop_path: str, expression: str) -> dict[str, Any]:
        return self.server.set_expression(doc_name, object_name, prop_path, expression)

    def clear_expression(self, doc_name: str, object_name: str, prop_path: str) -> dict[str, Any]:
        return self.server.clear_expression(doc_name, object_name, prop_path)

    def list_expressions(self, doc_name: str, object_name: str) -> dict[str, Any]:
        return self.server.list_expressions(doc_name, object_name)

    def body_create(self, doc_name: str, body_name: str) -> dict[str, Any]:
        return self.server.body_create(doc_name, body_name)

    def body_set_tip(self, doc_name: str, body_name: str, feature_name: str) -> dict[str, Any]:
        return self.server.body_set_tip(doc_name, body_name, feature_name)

    def sketch_attach(self, doc_name: str, sketch_name: str, support) -> dict[str, Any]:
        return self.server.sketch_attach(doc_name, sketch_name, support)

    def sketch_edit_constraint(
        self,
        doc_name: str,
        sketch_name: str,
        value: float | None = None,
        name: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        return self.server.sketch_edit_constraint(doc_name, sketch_name, value, name, index)

    def diagnose_parametric(self, doc_name: str, object_name: str | None = None) -> dict[str, Any]:
        return self.server.diagnose_parametric(doc_name, object_name)

    def recompute_document(self, doc_name: str) -> dict[str, Any]:
        return self.server.recompute_document(doc_name)

    def undo(self, doc_name: str) -> dict[str, Any]:
        return self.server.undo(doc_name)

    def redo(self, doc_name: str) -> dict[str, Any]:
        return self.server.redo(doc_name)

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        # The solver blocks the RPC response for up to `timeout` seconds, so the
        # socket must outlast it. The default 150 s transport timeout would abort
        # any solve longer than that even though the addon is still working.
        # Use a dedicated proxy whose socket timeout exceeds the solver timeout.
        proxy = self._make_proxy(max(self._timeout, timeout + 30))
        return proxy.run_fem_analysis(doc_name, analysis_name, timeout)
