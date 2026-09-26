# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
import os
import re

from pyrevit import forms, revit, script

from vdrop import calc, report, revit_vd, settings
from vdrop.parse import format_number

TITLE = "Voltage Drop"


def _doc():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to calculate the voltage drop.", title=TITLE)
        return None
    return doc


def _ready(doc):
    """True when lengths can be read. Offers to add the VD parameters and
    the schedule used to type the lengths."""
    missing = revit_vd.missing_parameters(doc)
    if not missing:
        return True
    add = forms.alert(
        "These voltage drop parameters are missing, or not yet on panels and fixtures:"
        "\n\n    %s\n\nAdd them now, with a '%s' schedule listing every panel to type "
        "the lengths in?" % ("\n    ".join(missing), revit_vd.SCHEDULE_NAME),
        yes=True, no=True, title=TITLE)
    if not add:
        return revit_vd.P_LENGTH not in missing
    try:
        schedule = revit_vd.setup(doc, missing)
    except Exception as error:
        forms.alert("Could not add the parameters: %s\n\nAdd them by hand as instance "
                    "parameters (see the README)." % error, title=TITLE)
        return False
    if schedule is not None:
        revit.uidoc.ActiveView = schedule
    forms.alert("Parameters added.\n\nFor each panel, type the length of its incoming cable "
                "in metres in VD Length%s.\n\nFor final circuits (AHU, pumps, lights...), "
                "type VD Length on the equipment or fixture; the farthest one counts.\n\n"
                "Then click Calculate VD again." % (
                    " (the '%s' schedule lists every panel)" % revit_vd.SCHEDULE_NAME
                    if schedule else ""),
                title=TITLE)
    return False


def _calculate(doc, values):
    model = revit_vd.collect(doc, values)
    result = calc.calculate(model.feeders, settings.calc_settings(values))
    return model, result


# ---------------------------------------------------------------- calculate

def _show(result, model, written):
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md("# Voltage drop")
    output.print_md(report.headline(result))
    notes = []
    if model.skipped:
        notes.append("%d final circuit%s without a VD Length left out." % (
            model.skipped, "" if model.skipped == 1 else "s"))
    if written:
        notes.append("VD Percent and VD Total Percent written on %d element%s." % (
            written, "" if written == 1 else "s"))
    for line in notes + model.warnings + result.warnings:
        output.print_md("- " + line)

    fixes = report.to_fix(result, revit_vd.SCHEDULE_NAME)
    if fixes:
        output.print_md("## To fix")
        for line in fixes:
            output.print_md("- " + line)

    attention = [r for r in result.rows() if r.status() != "OK"]
    if attention:
        output.print_md("## Needs a look")
        for row in attention:
            link = output.linkify(row.feeder.ref) if row.feeder.ref is not None else ""
            output.print_md(u"- **%s** %s -> %s: %s %s" % (
                row.number, row.feeder.source, row.feeder.target,
                report.result_text(row), link))
    for section in result.sections:
        output.print_table(table_data=report.table(section), columns=report.TABLE_COLUMNS,
                           title=section.title)


def calculate():
    doc = _doc()
    if doc is None or not _ready(doc):
        return
    values = settings.load()
    model, result = _calculate(doc, values)
    if not list(result.rows()):
        forms.alert("Nothing to calculate: no panel is fed from another panel or a "
                    "transformer, and no final circuit has a VD Length.", title=TITLE)
        return
    written = revit_vd.write_results(doc, result, model.elements)
    _show(result, model, written)


# ---------------------------------------------------------------- report

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


def _file_name(info):
    name = re.sub(r'[\\/:*?"<>|]+', " ", info.get("project") or "").strip()
    return ("%s Voltage Drop.xlsx" % name) if name else "Voltage Drop Calculation.xlsx"


def export_report():
    doc = _doc()
    if doc is None or not _ready(doc):
        return
    values = settings.load()
    model, result = _calculate(doc, values)
    if not list(result.rows()):
        forms.alert("Nothing to report: no panel is fed from another panel or a "
                    "transformer, and no final circuit has a VD Length.", title=TITLE)
        return
    project = revit_vd.project_info(doc)
    path = forms.save_file(file_ext="xlsx", default_name=_file_name(project))
    if not path:
        return
    info = report.ReportInfo(
        company=values["company"], project=project.get("project", ""),
        location=project.get("location", ""), client=project.get("client", ""),
        block=project.get("block", ""), revision=values["revision"],
        issue=values["issue"] or project.get("status", ""))
    try:
        report.build(result, settings.calc_settings(values), info).save(path)
    except Exception as error:
        forms.alert("Could not save the report:\n%s\n\nIf it is open in Excel, close it "
                    "and try again." % error, title=TITLE)
        return
    _open(path)
    forms.alert(report.headline(result), expanded="Saved to %s" % path, title=TITLE)


# ---------------------------------------------------------------- settings

# key, label, unit
_SETTINGS = [
    ("voltage_3ph", "Three phase voltage", "V"),
    ("voltage_1ph", "Single phase voltage", "V"),
    ("power_factor", "Power factor (when the circuit has none)", ""),
    ("load_basis", "Load for the current", ""),
    ("limit_transformer", "Max V.D transformer to main board", "%"),
    ("limit_total", "Max V.D to the final load", "%"),
    ("insulation", "Cable (when VD Cable doesn't say)", ""),
    ("installation", "Installation (when VD Installation is empty)", ""),
    ("air_temperature", "Air temperature, cable tray", u"°C"),
    ("ground_temperature", "Ground temperature, ground and duct bank", u"°C"),
    ("depth", "Laying depth, ground and duct bank (0 = not applied)", "mm"),
    ("soil_resistivity", "Soil thermal resistivity (0 = not applied)", "K.m/W"),
    ("grouping", "Grouping factor Cg", ""),
    ("company", "Report: company name", ""),
    ("revision", "Report: revision", ""),
    ("issue", "Report: issue (empty = Revit project status)", ""),
]

_BASIS = {calc.MDL: "MDL - demand load of the fed board",
          calc.TCL: "TCL - connected load"}


def _shown(key, value):
    if key == "load_basis":
        return _BASIS[value]
    if isinstance(value, float):
        return format_number(value, 3)
    return value


def _pick(key, label):
    options = [u"%s" % _shown(key, v) for v in settings.CHOICES[key]]
    choice = forms.CommandSwitchWindow.show(options, message=label + ":")
    if not choice:
        return None
    return settings.CHOICES[key][options.index(choice)]


def edit_settings():
    while True:
        values = settings.load()
        options = []
        for key, label, unit in _SETTINGS:
            shown = _shown(key, values[key])
            options.append(u"%s: %s%s" % (label, shown if shown != "" else "-",
                                          " " + unit if unit and shown != "" else ""))
        choice = forms.CommandSwitchWindow.show(options, message="Click a setting to change it:")
        if not choice:
            return
        key, label, unit = _SETTINGS[options.index(choice)]
        if key in settings.CHOICES:
            value = _pick(key, label)
            if value is None:
                continue
        else:
            text = forms.ask_for_string(default=u"%s" % _shown(key, values[key]),
                                        prompt=label + (" (%s)" % unit if unit else "") + ":",
                                        title="%s Settings" % TITLE)
            if text is None:
                continue
            value = settings.valid(key, text.replace(",", ".").strip()
                                   if isinstance(settings.DEFAULTS[key], float) else text.strip())
            if value is None:
                forms.alert("'%s' is not valid for %s." % (text, label.lower()), title=TITLE)
                continue
        values[key] = value
        settings.save(values)

