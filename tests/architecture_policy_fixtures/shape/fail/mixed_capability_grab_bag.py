"""Unrelated CAD capability families cannot share a production module."""

from capabilities.assembly.joints import add_assembly_joint as _add_assembly_joint
from capabilities.diagnostics.health import inspect_mesh_topology as _inspect_mesh_topology
from capabilities.drawing.pages import export_drawing_page as _export_drawing_page
from capabilities.fem.materials import apply_fem_material as _apply_fem_material
from capabilities.path.jobs import create_path_job as _create_path_job
from capabilities.render.video import render_video_frame as _render_video_frame
from capabilities.sketch.geometry import create_sketch_geometry as _create_sketch_geometry


def add_assembly_joint():
    return None


def apply_fem_material():
    return None


def create_path_job():
    return None


def create_sketch_geometry():
    return None


def export_drawing_page():
    return None


def inspect_mesh_topology():
    return None


def render_video_frame():
    return None


__all__ = (
    "add_assembly_joint",
    "apply_fem_material",
    "create_path_job",
    "create_sketch_geometry",
    "export_drawing_page",
    "inspect_mesh_topology",
    "render_video_frame",
)
