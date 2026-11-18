# -*- coding: utf-8 -*-
"""Entry point for the Export Panel Schedules button."""
import os
import re

from pyrevit import forms, revit, script

from panelsched import revit_panels, workbook

TITLE = "Panel Schedules"

ALL = "All panel schedules"
PICK = "Pick panel schedules"


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


def _natural(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text or u"")]


def _choose(doc, views):
    choice = forms.CommandSwitchWindow.show(
        [ALL, PICK], message="%d panel schedules in the model. Export:" % len(views))
    if choice == ALL:
        return views
    if choice == PICK:
        names = dict((u"%s  [%s]" % (revit_panels.panel_name(doc, v), v.Name), v) for v in views)
        picked = forms.SelectFromList.show(sorted(names, key=_natural), title=TITLE,
                                           multiselect=True, button_name="Export")
        return [names[p] for p in picked or []]
    return []


def _file_name(doc):
    name = re.sub(r'[\\/:*?"<>|]+', " ", doc.Title or "").strip()
    return ("%s Panel Schedules.xlsx" % name) if name else "Panel Schedules.xlsx"


def export():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to export its panel schedules.", title=TITLE)
        return
    views = sorted(revit_panels.schedule_views(doc),
                   key=lambda v: _natural(revit_panels.panel_name(doc, v)))
    if not views:
        forms.alert("This model has no panel schedules.\n\nCreate them in Revit first "
                    "(View > Schedules > Panel Schedules).", title=TITLE)
        return
    views = _choose(doc, views)
    if not views:
        return
    path = forms.save_file(file_ext="xlsx", default_name=_file_name(doc))
    if not path:
        return

    schedules, failed = [], []
    with forms.ProgressBar(title="Reading panel schedules ({value} of {max_value})") as bar:
        for n, view in enumerate(views, 1):
            try:
                schedules.append(revit_panels.read(doc, view))
            except Exception as error:
                failed.append((view.Name, error))
            bar.update_progress(n, len(views))
    if not schedules:
        forms.alert("No panel schedule could be read.", title=TITLE)
        return
    try:
        workbook.build(schedules, doc.Title or u"").save(path)
    except Exception as error:
        forms.alert("Could not save the file:\n%s\n\nIf it is open in Excel, close it "
                    "and try again." % error, title=TITLE)
        return

    if failed:
        output = script.get_output()
        output.set_title(TITLE)
        output.print_md("# Panel schedules")
        output.print_md(workbook.headline(schedules, path))
        output.print_md("## Not exported")
        for name, error in failed:
            output.print_md(u"- **%s**: %s" % (name, error))
    _open(path)
