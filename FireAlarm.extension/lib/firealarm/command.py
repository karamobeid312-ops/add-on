# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import ElementId
from pyrevit import forms, revit
from System.Collections.Generic import List

from firealarm import settings
from firealarm.report import summarize
from firealarm.revit_fa import (detector_types, pick_spaces, place_detectors,
                                placement_kind, selected_spaces)

TITLE = "Fire Alarm"


def _detector_type(doc, kind, values, ask=False):
    """The saved detector type, or the one picked from the loaded types."""
    types = detector_types(doc)
    if not types:
        forms.alert("No detector family is loaded in this model.\n\n"
                    "Load your detector family (Fire Alarm Devices category) and try again.",
                    title=TITLE)
        return None
    key = kind + "_type"
    if not ask and values[key] in types:
        return types[values[key]]
    label = forms.SelectFromList.show(sorted(types), title="%s detector type" % kind.title(),
                                      button_name="Use this type", multiselect=False)
    if not label:
        return None
    values[key] = label
    settings.save(values)
    return types[label]


def _ask_replace(count, spaces):
    answer = forms.alert(
        "%d detector%s of this type %s already in %d of the selected spaces."
        % (count, "" if count == 1 else "s", "is" if count == 1 else "are", spaces),
        options=["Replace them", "Keep them and add the new ones"], title=TITLE)
    if not answer:
        return None
    return answer.startswith("Replace")


def run(kind):
    """Place smoke or heat detectors in the selected spaces."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to place detectors.", title=TITLE)
        return
    values = settings.load()

    spaces = selected_spaces(uidoc) or pick_spaces(uidoc)
    if not spaces:
        return
    symbol = _detector_type(doc, kind, values)
    if symbol is None:
        return
    if placement_kind(symbol) is None:
        forms.alert("'%s' cannot be placed on a ceiling.\n\nUse a face-based, ceiling-hosted "
                    "or level-based family (change it in FA Settings)." % values[kind + "_type"],
                    title=TITLE)
        return

    answers = []

    def ask_replace(count, space_count):
        answers.append(_ask_replace(count, space_count))
        return answers[-1]

    plans = place_detectors(doc, spaces, symbol, values[kind + "_spacing"], values["clearance"],
                            "Place %s Detectors" % kind.title(), ask_replace)
    if plans is None:
        return

    placed = [i for p in plans for i in p.placed]
    if placed:
        uidoc.Selection.SetElementIds(List[ElementId](placed))
    headline, details = summarize(plans, kind, replaced=bool(answers and answers[0]))
    forms.alert(headline, expanded=details, title=TITLE)


# ---------------------------------------------------------------- settings

_SETTINGS = [
    ("smoke_spacing", "Smoke detector spacing", "m"),
    ("heat_spacing", "Heat detector spacing", "m"),
    ("clearance", "Min distance from walls", "m"),
    ("smoke_type", "Smoke detector type", ""),
    ("heat_type", "Heat detector type", ""),
]

_PROMPTS = {
    "smoke_spacing": "Max distance between smoke detectors (m).\n"
                     "Detectors are at most half of it from the walls.",
    "heat_spacing": "Max distance between heat detectors (m).\n"
                    "Detectors are at most half of it from the walls.",
    "clearance": "Min distance from walls and columns (m).\n"
                 "Relaxed only in spaces too narrow for it.",
}


def _number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")


def edit_settings():
    doc = revit.doc
    while True:
        values = settings.load()
        options = []
        for key, name, unit in _SETTINGS:
            value = values[key]
            if unit:
                value = "%s %s" % (_number(value), unit)
            options.append(u"%s: %s" % (name, value or "asked on first use"))
        choice = forms.CommandSwitchWindow.show(options, message="Click a setting to change it:")
        if not choice:
            return
        key = _SETTINGS[options.index(choice)][0]
        if key.endswith("_type"):
            if doc is None or doc.IsFamilyDocument:
                forms.alert("Open the project model to pick the detector type.", title=TITLE)
                continue
            _detector_type(doc, key[:-len("_type")], values, ask=True)
            continue
        text = forms.ask_for_string(default=_number(values[key]), prompt=_PROMPTS[key],
                                    title="%s Settings" % TITLE)
        if text is None:
            continue
        try:
            value = float(text.replace(",", ".").replace("m", "").strip())
        except ValueError:
            forms.alert("'%s' is not a number." % text, title=TITLE)
            continue
        if value < 0 or (value == 0 and key != "clearance"):
            forms.alert("Enter a positive length in metres.", title=TITLE)
            continue
        values[key] = value
        settings.save(values)
