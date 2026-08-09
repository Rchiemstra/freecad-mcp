from ..fem.meshes import create_mesh


def add_constraint(document, constraint):
    return create_mesh(document, constraint)
