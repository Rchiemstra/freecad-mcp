"""Document fixtures for assembly / measure / IO native qualification."""

from __future__ import annotations

import tempfile
from pathlib import Path


def prepare_assembly_document(document, kind: str) -> dict[str, str]:
    import FreeCAD

    ctx: dict[str, str] = {}
    if kind == "assembly":
        return ctx
    if kind == "assembly_with_base":
        from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_actions

        payload = assembly_actions.create_assembly(
            document,
            assembly_name="Assembly",
            create_joint_group=True,
            if_exists="error",
        )
        base = document.addObject("Part::Box", "Base")
        document.recompute()
        ctx["assembly"] = str(payload["assembly"])
        ctx["base"] = base.Name
        return ctx
    if kind == "assembly_with_two_parts":
        from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_actions

        payload = assembly_actions.create_assembly(
            document,
            assembly_name="Assembly",
            create_joint_group=True,
            if_exists="error",
        )
        part_a = document.addObject("Part::Box", "A")
        part_b = document.addObject("Part::Box", "B")
        part_b.Placement.Base = FreeCAD.Vector(20, 0, 0)
        document.recompute()
        ctx["assembly"] = str(payload["assembly"])
        ctx["a"] = part_a.Name
        ctx["b"] = part_b.Name
        return ctx
    if kind == "assembly_only":
        from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_actions

        payload = assembly_actions.create_assembly(
            document,
            assembly_name="Assembly",
            create_joint_group=True,
            if_exists="error",
        )
        document.recompute()
        ctx["assembly"] = str(payload["assembly"])
        return ctx
    if kind == "box":
        import Part

        box = document.addObject("Part::Feature", "Box")
        box.Shape = Part.makeBox(10, 10, 10)
        document.recompute()
        ctx["box"] = box.Name
        return ctx
    if kind == "volume":
        mover = document.addObject("Part::Box", "Mover")
        mover.Length = 5
        wall = document.addObject("Part::Box", "Wall")
        wall.Length = 30
        wall.Placement.Base = FreeCAD.Vector(15, 0, 0)
        document.recompute()
        ctx["mover"] = mover.Name
        ctx["wall"] = wall.Name
        return ctx
    raise KeyError(kind)


def export_temp_path(suffix: str) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    return handle.name


def write_box_brep(path: str) -> None:
    import Part

    shape = Part.makeBox(10, 10, 10)
    shape.exportBrep(path)


def write_box_step(path: str) -> None:
    import Part

    shape = Part.makeBox(10, 10, 10)
    shape.exportStep(path)
