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
    ) -> str | None:
        try:
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

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        # The solver blocks the RPC response for up to `timeout` seconds, so the
        # socket must outlast it. The default 150 s transport timeout would abort
        # any solve longer than that even though the addon is still working.
        # Use a dedicated proxy whose socket timeout exceeds the solver timeout.
        proxy = self._make_proxy(max(self._timeout, timeout + 30))
        return proxy.run_fem_analysis(doc_name, analysis_name, timeout)
