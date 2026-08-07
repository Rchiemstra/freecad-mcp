from capabilities.mesh.topology import create_mesh as _create_mesh
from capabilities.sketch.constraints import add_constraint as _add_constraint


def add_constraint(document, constraint):
    return document, constraint


def create_mesh(document):
    return document
