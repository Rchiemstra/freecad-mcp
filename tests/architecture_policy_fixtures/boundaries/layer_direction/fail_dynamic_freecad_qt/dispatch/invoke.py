import builtins
from builtins import __import__ as imported_builtin

direct_alias = __import__
qualified_alias = builtins.__import__


freecad = __import__("FreeCAD")
freecad_gui = builtins.__import__("FreeCADGui")
qt = imported_builtin("PySide6")
part = qualified_alias("Part")
transport = __import__("addon.FreeCADMCP.transport.listener")
runtime = __import__("addon.FreeCADMCP.runtime")
