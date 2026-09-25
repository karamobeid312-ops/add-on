# -*- coding: utf-8 -*-
"""Shared entry point for the ribbon buttons."""
from pyrevit import forms, revit

from sld.revit_sld import generate


def run(include_branch_circuits):
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to generate a single line diagram.", exitscript=True)

    view, diagram = generate(doc, include_branch_circuits)
    if view is None:
        forms.alert("No electrical equipment was found in this model.\n\n"
                    "Place panels/switchboards and connect them with circuits first.",
                    exitscript=True)

    revit.uidoc.ActiveView = view
    if diagram.warnings:
        forms.alert("Diagram created in '%s' with %d warning(s):" % (view.Name, len(diagram.warnings)),
                    expanded="\n".join(diagram.warnings))
