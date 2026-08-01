# SPDX-License-Identifier: LGPL-2.1-or-later

from .validation import require_document


def createAssembly(doc=None, name="Assembly", *, createJointGroup=True, recompute=False):
    doc = require_document(doc)

    assembly = doc.addObject("Assembly::AssemblyObject", name)
    assembly.Type = "Assembly"

    if createJointGroup:
        import UtilsAssembly

        UtilsAssembly.getJointGroup(assembly)

    if recompute:
        doc.recompute()

    return assembly
