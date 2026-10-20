# -*- coding: utf-8 -*-
"""Power Studio: the LV schematic and the voltage drop in one window."""
import os
import re

from pyrevit import forms, revit

from sld import settings


def _project(doc):
    return doc.PathName or doc.Title


def _editor(doc, values):
    from sld.editor import Editor
    from sld.model import build_schematic
    from sld.revit_sld import extract
    live = {}
    equipment, circuits, phases_of, warnings = extract(doc, live)
    settings.apply_spares(equipment, settings.load_spares(_project(doc)))
    schematic = build_schematic(equipment, circuits, phases_of, values["numbering"])
    schematic.warnings = warnings + schematic.warnings
    return Editor(schematic, live or None, values["numbering"])


def _save(doc, editor):
    """Save to Revit, with the V.D results; returns the message shown."""
    from sld import revit_edit
    from vdrop import revit_vd
    changes = editor.changes()
    lines = []
    spares = [c for c in changes if c.kind == "spares"]
    if spares:
        # kept here too: most models have no SLD Spares parameter to hold them
        stored = settings.load_spares(_project(doc))
        for c in spares:
            stored[editor.board(c.element_id).name] = (c.values["count"], c.values["rating"],
                                                       c.values.get("spaces", ""))
        try:
            settings.save_spares(_project(doc), stored)
            lines.append("Spare ways kept for the SLD (drawn only, the Revit panels are not changed).")
        except Exception as error:
            lines.append("Spares not kept: %s" % error)
    if changes:
        written, skipped, _ = revit_edit.save(doc, changes)
        editor.mark_saved()
        lines.append("%d value(s) written to Revit." % written)
        if skipped:
            lines.append("Not written:")
            lines += ["- %s" % s for s in skipped]
    else:
        lines.append("No changes to save.")
    if editor.result is not None and editor.vd and editor.vd.get("elements"):
        try:
            n = revit_vd.write_results(doc, editor.result, editor.vd["elements"])
        except Exception as error:
            lines.append("V.D results not written: %s" % error)
        else:
            if n:
                lines.append("VD Percent and VD Total Percent written on %d element(s)." % n)
    return "\n".join(lines)


def _keep_settings(sld_values, vd_values):
    from vdrop import settings as vd_settings
    settings.save(sld_values)
    vd_settings.save(vd_values)


def _report_name(doc):
    from vdrop import revit_vd
    name = re.sub(r'[\\/:*?"<>|]+', " ", revit_vd.project_info(doc).get("project") or "")
    name = name.strip()
    return ("%s Voltage Drop.xlsx" % name) if name else "Voltage Drop Calculation.xlsx"


def _open(path):
    try:
        os.startfile(path)
        return
    except Exception:
        pass
    try:
        from System.Diagnostics import Process, ProcessStartInfo
        start = ProcessStartInfo(path)
        start.UseShellExecute = True   # needed to open a document on .NET 8
        Process.Start(start)
    except Exception:
        pass


def _report(doc, editor, path):
    """The office voltage drop sheet (Excel, then PDF made by Excel) of the
    values shown in the window. Returns the message shown."""
    from vdrop import excel, report, revit_vd
    from vdrop import settings as vd_settings
    values = vd_settings.load()
    project = revit_vd.project_info(doc)
    info = report.ReportInfo(
        company=values["company"], project=project.get("project", ""),
        location=project.get("location", ""), client=project.get("client", ""),
        block=project.get("block", ""), revision=values["revision"],
        issue=values["issue"] or project.get("status", ""))
    try:
        report.build(editor.result, editor.vd["settings"], info).save(path)
    except Exception as error:
        return (u"Could not save the report:\n%s\n\nIf it is open in Excel, close it and "
                u"try again." % error)
    headline = report.headline(editor.result)
    if editor.dirty():
        headline += u"\n\nThe report has your unsaved changes; Save to Revit to keep them."
    pdf_path = os.path.splitext(path)[0] + ".pdf"
    try:
        excel.save_pdf(path, pdf_path)
    except Exception as error:
        _open(path)
        return (u"%s\n\nExcel saved: %s\n\nThe PDF was not made: %s. If it is open in a "
                u"viewer, close it and try again." % (headline, path, error))
    _open(pdf_path)
    return u"%s\n\nExcel: %s\nPDF: %s" % (headline, path, pdf_path)


def _model_text(doc, editor):
    from vdrop import revit_vd
    name = revit_vd.project_info(doc).get("project") or doc.Title
    ways = sum(len(editor.ways(b.id)) for b in editor.boards)
    return u"%s\n%d boards · %d ways" % (name, len(editor.boards), ways)


def run():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to open Power Studio.", exitscript=True)

    from sld.editor_ui import show_editor
    from vdrop import settings as vd_settings
    sld_values, vd_values = settings.load(), vd_settings.load()
    actions = {"save": lambda ed: _save(doc, ed), "settings": _keep_settings,
               "report": lambda ed, path: _report(doc, ed, path),
               "report_name": _report_name(doc),
               "save_risers": lambda specs: settings.save_risers(_project(doc), specs),
               "save_generators": lambda specs: settings.save_generators(_project(doc), specs),
               "save_supplies": lambda specs: settings.save_supplies(_project(doc), specs)}
    action = "reload"
    while action == "reload":         # again after a Fed from or a model setting changed
        actions["risers"] = settings.load_risers(_project(doc))
        actions["generators"] = settings.load_generators(_project(doc))
        actions["supplies"] = settings.load_supplies(_project(doc))
        editor = _editor(doc, sld_values)
        if not editor.boards:
            forms.alert("No electrical equipment was found in this model.\n\n"
                        "Place panels/switchboards and connect them with circuits first.",
                        exitscript=True)
        action, sld_values, vd_values = show_editor(editor, sld_values, vd_values, actions,
                                                    _model_text(doc, editor))
    if action != "generate":
        return
    if editor.dirty():
        _save(doc, editor)

    from sld.revit_sld import generate
    view, schematic = generate(doc, settings.layout_settings(sld_values),
                               sld_values["numbering"], bool(sld_values.get("new_view")),
                               spares=settings.load_spares(_project(doc)),
                               paper=sld_values.get("sheet_size", "A1"),
                               risers=settings.load_risers(_project(doc)),
                               generators=settings.load_generators(_project(doc)),
                               supplies=settings.load_supplies(_project(doc)))
    if view is None:
        forms.alert("No electrical equipment was found in this model.", exitscript=True)
    revit.uidoc.ActiveView = view
    if schematic.warnings:
        forms.alert("Diagram drawn in '%s' with %d warning(s):" % (view.Name, len(schematic.warnings)),
                    expanded="\n".join(schematic.warnings))
