import unittest

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.core import execute_code_operation


class FakeFreeCAD:
    def __init__(self):
        self.executed_code = None
        self.screenshot_request = None

    def execute_code(self, code):
        self.executed_code = code
        return {"success": True, "message": "ok"}

    def get_active_screenshot(
        self,
        view_name="Isometric",
        width=None,
        height=None,
        focus_object=None,
    ):
        self.screenshot_request = (view_name, width, height, focus_object)
        return "encoded-image"


class FakeRpcServer:
    def __init__(self):
        self.screenshot_request = None

    def execute_code(self, code):
        return {
            "success": True,
            "message": "Current view supports screenshots: Gui::View3DInventor",
        }

    def get_active_screenshot(self, view_name, width, height, focus_object):
        self.screenshot_request = (view_name, width, height, focus_object)
        return "encoded-image"


class ExecuteCodeCameraTest(unittest.TestCase):
    def test_execute_code_screenshot_preserves_active_camera(self):
        freecad = FakeFreeCAD()

        execute_code_operation(freecad, only_text_feedback=False, code="print('hello')")

        self.assertEqual(freecad.executed_code, "print('hello')")
        self.assertEqual(freecad.screenshot_request, (None, None, None, None))

    def test_client_forwards_none_view_name_to_rpc(self):
        rpc_server = FakeRpcServer()
        connection = object.__new__(FreeCADConnection)
        connection.server = rpc_server

        screenshot = connection.get_active_screenshot(view_name=None)

        self.assertEqual(screenshot, "encoded-image")
        self.assertEqual(rpc_server.screenshot_request, (None, None, None, None))
