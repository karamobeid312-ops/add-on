# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import ElementId
from pyrevit import forms, revit
from System.Collections.Generic import List

from dims import revit_dims, settings
from dims.report import summarize
from firealarm.revit_fa import linked_models, pick_linked_spaces, pick_spaces

TITLE = "Dimensions"

ALL = "All devices in this view"
PICK = "Pick devices"
PICK_SPACES = "Devices in spaces or rooms I pick"
PICK_LINKED = "Devices in spaces or rooms I pick in a linked model"

CATEGORY_NAMES = ("fire alarm devices, lighting fixtures and devices, electrical fixtures, "
                  "communication, data, security, nurse call and telephone devices, "
                  "generic models")


def _categories(instances):
    """The instances, or those of the categories picked when there are several."""
    groups = revit_dims.by_category(instances)
    if len(groups) <= 1:
        return instances
    labels = [u"%s (%d)" % (name, len(found)) for name, found in groups]
    chosen = forms.SelectFromList.show(labels, title="Dimension which devices?",
                                       button_name="Dimension", multiselect=True)
    if not chosen:
        return []
    return [i for label, (_, found) in zip(labels, groups) if label in chosen for i in found]


def _choose(doc, uidoc, view):
    """(instances to dimension, selected devices not shown in the view).
    The devices selected before clicking, or in the selected spaces, or
    picked / taken from the view now."""
    devices, spaces = revit_dims.selection(uidoc)
    if not devices and not spaces:
        options = [ALL, PICK, PICK_SPACES] + ([PICK_LINKED] if linked_models(doc) else [])
        choice = forms.CommandSwitchWindow.show(options, message="Which devices get dimensions?")
        if choice == ALL:
            found = revit_dims.view_devices(doc, view)
            if not found:
                forms.alert("No devices are shown in this view.\n\nDevices are family "
                            "instances of these categories: %s." % CATEGORY_NAMES, title=TITLE)
            return _categories(found), 0
        if choice == PICK:
            return _categories(revit_dims.pick_devices(uidoc)), 0
        if choice == PICK_SPACES:
            spaces = pick_spaces(uidoc)
        elif choice == PICK_LINKED:
            spaces = pick_linked_spaces(uidoc)
        if not spaces:
            return [], 0
    visible = revit_dims.visible_ids(doc, view)
    shown = [d for d in devices if revit_dims.id_int(d.Id) in visible]
    hidden = len(devices) - len(shown)
    if spaces:
        known = set(revit_dims.id_int(d.Id) for d in shown)
        inside = revit_dims.in_spaces(revit_dims.view_devices(doc, view), spaces)
        shown += [d for d in inside if revit_dims.id_int(d.Id) not in known]
        if not shown:
            forms.alert("No devices shown in this view are in the selected spaces.\n\nDevices "
                        "are family instances of these categories: %s." % CATEGORY_NAMES,
                        title=TITLE)
            return [], hidden
    return _categories(shown), hidden


def _ask_replace(count):
    answer = forms.alert(
        "%d dimension%s in this view already go%s to these devices."
        % (count, "" if count == 1 else "s", "es" if count == 1 else ""),
        options=["Replace them", "Keep them and add the new ones"], title=TITLE)
    if not answer:
        return None
    return answer.startswith("Replace")


def run():
    """Dimension the chosen devices in the active plan."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to dimension devices.", title=TITLE)
        return
    view = doc.ActiveView
    if not revit_dims.is_plan(view):
        forms.alert("Open a floor plan or a ceiling plan: the dimensions go in the active view.",
                    title=TITLE)
        return
    values = settings.load()

    instances, hidden = _choose(doc, uidoc, view)
    if not instances:
        if hidden:
            forms.alert("The selected devices are not shown in this view.", title=TITLE)
        return
    devices, notes = revit_dims.read_devices(instances)
    if not devices:
        forms.alert("None of these devices can be dimensioned, see why in the details.",
                    title=TITLE,
                    expanded="\n".join(u"%s (%d): %s." % (label, count, note)
                                       for (label, note), count in sorted(notes.items())))
        return

    old_helpers = revit_dims.helper_lines(doc, view, devices)
    old = revit_dims.dimensions_to(doc, view, [d.key for d in devices] + old_helpers)
    replace = False
    if old:
        replace = _ask_replace(len(old))
        if replace is None:
            return

    dim_type = None
    if values["dim_type"]:
        dim_type = revit_dims.dimension_types(doc).get(values["dim_type"])
    result = revit_dims.dimension(
        doc, view, devices, dim_type, values["offset"], every_row=values["strings"] == "every",
        walls=values["ends"], old=old if replace else (),
        old_helpers=old_helpers if replace else ())
    result.notes, result.hidden = notes, hidden
    if values["dim_type"] and dim_type is None:
        result.type_missing = values["dim_type"]
    result.dims_hidden = revit_dims.dimensions_hidden(view)

    if result.made:
        uidoc.Selection.SetElementIds(List[ElementId](result.made))
    headline, details = summarize(result)
    forms.alert(headline, expanded=details or None, title=TITLE)


# ---------------------------------------------------------------- settings

_SETTINGS = [
    ("dim_type", "Dimension type"),
    ("offset", "Dimension line from the devices"),
    ("strings", "Strings"),
    ("ends", "Walls"),
]

_SHOWN = {
    "strings": {"every": "every row and column",
                "needed": "only what is needed to place every device"},
    "ends": {"nearest": "nearest wall only", "both": "both walls (wall to wall)",
             "none": "none (between devices only)"},
}


def _number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")


def _shown(doc, key, value):
    if key == "dim_type":
        if value:
            return value
        default = revit_dims.default_type_name(doc) if doc is not None else ""
        return "the model's default" + (u" (%s)" % default if default else "")
    if key == "offset":
        return "%s mm on the printed sheet" % _number(value)
    return _SHOWN[key][value]


def _pick_type(doc, values):
    types = revit_dims.dimension_types(doc)
    if not types:
        forms.alert("There are no linear dimension types in this model.", title=TITLE)
        return
    default = u"The model's default (%s)" % revit_dims.default_type_name(doc)
    label = forms.SelectFromList.show([default] + sorted(types), title="Dimension type",
                                      button_name="Use this type", multiselect=False)
    if not label:
        return
    values["dim_type"] = "" if label == default else label
    settings.save(values)


def edit_settings():
    doc = revit.doc
    if doc is not None and doc.IsFamilyDocument:
        doc = None
    while True:
        values = settings.load()
        options = [u"%s: %s" % (label, _shown(doc, key, values[key])) for key, label in _SETTINGS]
        choice = forms.CommandSwitchWindow.show(options, message="Click a setting to change it:")
        if not choice:
            return
        key, label = _SETTINGS[options.index(choice)]
        if key == "dim_type":
            if doc is None:
                forms.alert("Open the project model to pick the dimension type.", title=TITLE)
            else:
                _pick_type(doc, values)
            continue
        if key in settings.CHOICES:
            shown = [_SHOWN[key][v] for v in settings.CHOICES[key]]
            picked = forms.CommandSwitchWindow.show(shown, message=label + ":")
            if not picked:
                continue
            values[key] = settings.CHOICES[key][shown.index(picked)]
        else:
            text = forms.ask_for_string(
                default=_number(values[key]),
                prompt="Distance from the devices to the dimension line, in mm on the printed "
                       "sheet (0 = through the devices):",
                title="%s Settings" % TITLE)
            if text is None:
                continue
            value = settings.valid(key, text.replace(",", ".").replace("mm", "").strip())
            if value is None:
                forms.alert("Enter a distance from 0 to %s mm." % _number(settings.MAX_OFFSET),
                            title=TITLE)
                continue
            values[key] = value
        settings.save(values)
