import FreeCAD as FreeCAD


def add_constraint(document, constraint):
    return document.addObject("PartDesign::Feature", constraint)
