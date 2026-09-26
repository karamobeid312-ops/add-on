# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from pyrevit import forms, revit

from sld import settings
from sld.revit_sld import generate


def run():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to generate the LV schematic diagram.", exitscript=True)

    values = settings.load()
    view, schematic = generate(doc, settings.layout_settings(values), values["numbering"])
    if view is None:
        forms.alert("No electrical equipment was found in this model.\n\n"
                    "Place panels/switchboards and connect them with circuits first.",
                    exitscript=True)

    revit.uidoc.ActiveView = view
    if schematic.warnings:
        forms.alert("Diagram created in '%s' with %d warning(s):" % (view.Name, len(schematic.warnings)),
                    expanded="\n".join(schematic.warnings))


def edit_settings():
    values = settings.load()
    utility = forms.ask_for_string(
        default=values["utility"], prompt="Utility / supply authority name (FROM TAQA):",
        title="SLD Settings")
    if utility is None:
        return
    label = forms.ask_for_string(
        default=values["substation_label"], prompt="Label of the bottom band:",
        title="SLD Settings")
    if label is None:
        return
    ratings = forms.alert("Print breaker rating and cable along each way?",
                          yes=True, no=True, title="SLD Settings")
    numbering = forms.CommandSwitchWindow.show(
        ["Ways from slots (1, 2, R9, Y9, B9)", "Revit circuit numbers"],
        message="Way numbering:")
    if numbering is None:
        return
    values.update({
        "utility": utility.strip().upper() or values["utility"],
        "substation_label": label.strip().upper() or values["substation_label"],
        "show_ratings": bool(ratings),
        "numbering": "slots" if numbering.startswith("Ways") else "revit",
    })
    settings.save(values)
    forms.alert("Settings saved.", title="SLD Settings")
