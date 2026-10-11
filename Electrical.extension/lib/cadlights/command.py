# -*- coding: utf-8 -*-
"""CAD Lights button: pick the DWG, map its blocks to fixture types, place."""
import time

from Autodesk.Revit.DB import ElementId, ViewPlan
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import forms, revit
from System.Collections.Generic import List

from cadlights import settings
from cadlights.match import SKIP, group, summarize
from cadlights.revit_cad import cad_label, is_cad, light_types, place_lights, read_blocks
from cadlights.window import TITLE, MappingWindow


class _CadFilter(ISelectionFilter):
    __namespace__ = "CadLights"         # needed by the CPython engine

    def AllowElement(self, element):
        return is_cad(element)

    def AllowReference(self, reference, position):
        return False


def _pick_cad(doc, uidoc):
    for element_id in uidoc.Selection.GetElementIds():
        element = doc.GetElement(element_id)
        if is_cad(element):
            return element
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, _CadFilter(),
                                         "Click the CAD (DWG) with the lights")
    except OperationCanceledException:
        return None
    return doc.GetElement(ref.ElementId)


def run():
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to place lights.", title=TITLE)
        return
    view = doc.ActiveView
    level = getattr(view, "GenLevel", None) if isinstance(view, ViewPlan) else None
    if level is None:
        forms.alert("Open the floor plan or ceiling plan that shows the CAD, then try again.\n\n"
                    "The lights are placed on that plan's level.", title=TITLE)
        return
    types = light_types(doc)
    if not types:
        forms.alert("No lighting fixture family is loaded in this model.\n\n"
                    "Load your light families (Lighting Fixtures category) and try again.",
                    title=TITLE)
        return

    cad = _pick_cad(doc, uidoc)
    if cad is None:
        return
    started = time.time()
    blocks = read_blocks(doc, cad, view)
    read_time = time.time() - started
    if not blocks:
        forms.alert("No blocks found in this CAD.\n\nThe lights must be blocks in the DWG "
                    "(lines and circles alone cannot be read). If the CAD was imported and "
                    "exploded, link or import it again without exploding.", title=TITLE)
        return
    rows = group(blocks)

    values = settings.load()
    chosen = settings.mapping(values)
    window = MappingWindow(cad_label(cad), level.Name,
                           [(name, len(items), layers) for name, items, layers in rows],
                           sorted(types), chosen, values["height_mm"], values["tolerance_mm"])
    picked = window.show()
    if picked is None:
        return
    values["height_mm"], values["tolerance_mm"] = window.height_mm, window.tolerance_mm
    settings.save(values, picked)

    jobs, skipped = [], []
    for name, items, _ in rows:
        label = picked.get(name, SKIP)
        if label == SKIP or label not in types:
            skipped.append(name)
        else:
            jobs.append((name, items, label, types[label]))

    results, placed, timings = place_lights(doc, level, jobs, values["height_mm"],
                                   values["tolerance_mm"], "Place CAD Lights")
    if placed:
        uidoc.Selection.SetElementIds(List[ElementId](placed))
    headline, details = summarize(results, skipped, [("read CAD", read_time)] + timings)
    forms.alert(headline, expanded=details, title=TITLE)
