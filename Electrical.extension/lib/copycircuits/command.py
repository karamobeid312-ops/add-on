# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import ElementId, TransactionGroup
from pyrevit import forms, revit, script
from System.Collections.Generic import List

from copycircuits import report, revit_copy, settings

TITLE = "Copy Circuits"
MM_PER_FOOT = 304.8


def _pick_levels(doc, view):
    all_levels = revit_copy.levels(doc)
    names = [l.Name for l in all_levels]
    by_name = dict((l.Name, l) for l in all_levels)
    if len(all_levels) < 2:
        forms.alert("The model needs at least two levels.", title=TITLE)
        return None, None
    try:
        here = view.GenLevel.Name
    except Exception:
        here = None
    ordered = ([here] if here in by_name else []) + [n for n in names if n != here]
    source = forms.SelectFromList.show(
        ordered, title="%s: copy the circuits of which floor?" % TITLE,
        button_name="Next", multiselect=False)
    if not source:
        return None, None
    targets = forms.SelectFromList.show(
        [n for n in names if n != source],
        title="%s: make them on which floors? (the copies of %s)" % (TITLE, source),
        button_name="Copy circuits", multiselect=True)
    if not targets:
        return None, None
    return by_name[source], [by_name[n] for n in names if n in targets]


def _show(output, result, source):
    source_name = source.level.Name
    output.print_md("## " + result.level)
    output.print_md(report.headline(result))
    if result.made:
        ids = [m.key for m in result.made]
        output.print_md(output.linkify(ids, "Select the %d new circuits" % len(ids)))
        output.print_table(
            table_data=[report.made_row(m, output.linkify(m.key)) for m in result.made],
            columns=report.MADE_COLUMNS)
    if result.failed:
        output.print_md("### Refused by Revit")
        output.print_table(
            table_data=[[j.circuit.label, msg] for j, msg in result.failed],
            columns=report.SKIPPED_COLUMNS)
    if result.skipped:
        output.print_md("### Not copied")
        output.print_table(table_data=[report.skipped_row(s) for s in result.skipped],
                           columns=report.SKIPPED_COLUMNS)
    missing = result.missing()
    if missing:
        output.print_md("%s on %s with no copy here, left out of their circuits: %s" % (
            len(missing) == 1 and "1 element" or "%d elements" % len(missing), source_name,
            output.linkify([source.elements[k].Id for k in missing], "select them")))
    if result.left:
        output.print_md("%d element%s of the same family types on %s matched nothing on %s "
                         "(new on this floor) and have no circuit: %s" % (
                             len(result.left), "" if len(result.left) == 1 else "s",
                             result.level, source_name,
                             output.linkify(result.left, "select them")))
    for line in report.wire_lines(result):
        output.print_md("- " + line)


def run():
    """Make the circuits of one floor on the floors copied from it."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to copy circuits.", title=TITLE)
        return
    source_level, targets = _pick_levels(doc, doc.ActiveView)
    if source_level is None:
        return
    chosen = set(revit_copy.id_int(i) for i in uidoc.Selection.GetElementIds()) or None
    values = settings.load()
    tolerance = values["tolerance"] / MM_PER_FOOT
    source = revit_copy.read_source(doc, source_level, chosen)
    if not source.circuits:
        forms.alert("No circuits found with elements on %s%s." % (
            source_level.Name, " among the selected elements" if chosen else ""), title=TITLE)
        return
    wires = revit_copy.Wires(doc, source_level) if values["wires"] else None

    results = []
    group = TransactionGroup(doc, TITLE)
    group.Start()
    try:
        for level in targets:
            results.append(revit_copy.copy_to(doc, source, level, tolerance, wires))
        group.Assimilate()
    except Exception:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise

    made = [m.key for r in results for m in r.made]
    if made:
        uidoc.Selection.SetElementIds(List[ElementId](made))
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md("# Circuits of %s copied" % source_level.Name)
    output.print_md("%d circuit%s read on %s%s; copies matched by family type and plan "
                    "position within %s mm." % (
                        len(source.circuits), "" if len(source.circuits) == 1 else "s",
                        source_level.Name, " (from the selection)" if chosen else "",
                        _number(values["tolerance"])))
    for result in results:
        _show(output, result, source)
    output.print_md("*The new circuits are selected in Revit. Undo once to take them all "
                    "back. Check the circuit numbers in the panel schedules.*")


def _number(value):
    return ("%.1f" % value).rstrip("0").rstrip(".")


def edit_settings():
    values = settings.load()
    text = forms.ask_for_string(
        default=_number(values["tolerance"]),
        prompt="Tolerance in mm: a fixture or panel this near the source one's spot in plan, "
               "of the same family type, is its copy (up to %s):"
               % _number(settings.MAX_TOLERANCE),
        title="%s Settings" % TITLE)
    if text is None:
        return
    value = settings.valid("tolerance", text.replace(",", ".").replace("mm", "").strip())
    if value is None:
        forms.alert("Enter a tolerance above 0 and up to %s mm."
                    % _number(settings.MAX_TOLERANCE), title=TITLE)
        return
    values["tolerance"] = value
    values["wires"] = forms.alert(
        "Draw the wires again on the copied floors?\n\n"
        "Yes: each wire in the source floor's plans is drawn in the copied floor's plan "
        "of the same kind, between the copies. Wires pasted with the fixtures but not "
        "connected are replaced.\nNo: circuits only.",
        title="%s Settings" % TITLE, yes=True, no=True)
    settings.save(values)
