# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import ElementId
from pyrevit import forms, revit, script
from System.Collections.Generic import List

from wallcheck import check, report, revit_check, settings

TITLE = "Wall Fixtures"

ALL = "All fixtures in the model"
VIEW = "Fixtures shown in this view"
PICK = "Pick fixtures"


def _choose(doc, uidoc):
    found = revit_check.selection(uidoc)
    if found:
        return found
    choice = forms.CommandSwitchWindow.show([ALL, VIEW, PICK],
                                            message="Which fixtures are checked?")
    if choice == ALL:
        return revit_check.model_fixtures(doc)
    if choice == VIEW:
        return revit_check.model_fixtures(doc, doc.ActiveView)
    if choice == PICK:
        return revit_check.pick_fixtures(uidoc)
    return []


def _show(result, total):
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md("# Wall fixtures")
    output.print_md(report.headline(result))
    problems = result.problems()
    if problems:
        ids = [f.fixture.key for f in problems]
        output.print_md("%s (they are selected in Revit too)" % output.linkify(
            ids, "Select all %d" % len(ids)))
    for title, fix, findings in report.sections(result):
        output.print_md("## " + title)
        output.print_md("*To fix: %s.*" % fix)
        output.print_table(
            table_data=[report.row(f, output.linkify(f.fixture.key)) for f in findings],
            columns=report.COLUMNS)
    notes = report.notes(result)
    if notes:
        output.print_md("## Not checked")
        for line in notes:
            output.print_md("- " + line)
    output.print_md("*%d fixture%s read. Click an element id to select it and zoom to it.*"
                    % (total, "" if total == 1 else "s"))


def run():
    """Check the chosen fixtures against their walls."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to check the wall fixtures.", title=TITLE)
        return
    instances = _choose(doc, uidoc)
    if not instances:
        return
    tolerance = settings.load()["tolerance"] / 1000.0
    result = check.check_all(revit_check.read_fixtures(instances), tolerance)
    problems = result.problems()
    if problems:
        uidoc.Selection.SetElementIds(List[ElementId]([f.fixture.key for f in problems]))
    _show(result, len(instances))


def _number(value):
    return ("%.1f" % value).rstrip("0").rstrip(".")


def edit_settings():
    values = settings.load()
    text = forms.ask_for_string(
        default=_number(values["tolerance"]),
        prompt="Tolerance in mm: a fixture this near its wall face is on the wall "
               "(0 to %s):" % _number(settings.MAX_TOLERANCE),
        title="%s Settings" % TITLE)
    if text is None:
        return
    value = settings.valid("tolerance", text.replace(",", ".").replace("mm", "").strip())
    if value is None:
        forms.alert("Enter a tolerance from 0 to %s mm." % _number(settings.MAX_TOLERANCE),
                    title=TITLE)
        return
    values["tolerance"] = value
    settings.save(values)
