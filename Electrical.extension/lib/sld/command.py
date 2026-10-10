# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from pyrevit import forms, revit

from sld import settings
from sld.revit_sld import extract, generate


def _editor(doc, values):
    from sld.editor import Editor
    from sld.model import build_schematic
    live = {}
    equipment, circuits, phases_of, warnings = extract(doc, live)
    schematic = build_schematic(equipment, circuits, phases_of, values["numbering"])
    schematic.warnings = warnings + schematic.warnings
    return Editor(schematic, live or None, values["numbering"])


def _save(doc, editor):
    """Save to Revit; returns the message shown in the window."""
    from sld import revit_edit
    changes = editor.changes()
    if not changes:
        return "Nothing to save."
    written, skipped, added = revit_edit.save(doc, changes)
    editor.mark_saved()
    lines = ["%d value(s) written to Revit." % written]
    if added:
        lines.append("Parameters added to the project: %s." % ", ".join(added))
    if skipped:
        lines.append("Not written:")
        lines += ["- %s" % s for s in skipped]
    return "\n".join(lines)


def run():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to generate the LV schematic diagram.", exitscript=True)

    from sld.editor_ui import show_editor
    values = settings.load()
    editor = _editor(doc, values)
    if not editor.boards:
        forms.alert("No electrical equipment was found in this model.\n\n"
                    "Place panels/switchboards and connect them with circuits first.",
                    exitscript=True)
    action, new_values = show_editor(editor, values, lambda ed: _save(doc, ed))
    if new_values and new_values != values:
        values.update(new_values)
        settings.save(values)
    if action != "generate":
        return
    if editor.dirty():
        _save(doc, editor)

    view, schematic = generate(doc, settings.layout_settings(values), values["numbering"])
    if view is None:
        forms.alert("No electrical equipment was found in this model.", exitscript=True)
    revit.uidoc.ActiveView = view
    if schematic.warnings:
        forms.alert("Diagram created in '%s' with %d warning(s):" % (view.Name, len(schematic.warnings)),
                    expanded="\n".join(schematic.warnings))


def edit_settings():
    """The settings are on the editor's Settings tab."""
    run()
