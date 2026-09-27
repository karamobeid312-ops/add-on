# -*- coding: utf-8 -*-
"""Revit side of Draw FA Loop: fire alarm devices of a plan view ->
loops (firealarm.loops) -> detail lines in that view.

Every loop leaves the start (the panel, or the device clicked first),
passes each of its devices once and comes back. Each loop has its own
line style, FA Loop 1, FA Loop 2... (subcategories of Lines, made with a
colour the first time; change them in Object Styles). Lines stop at the
edge of each device.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math
import re

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Color, CurveElement, ElementId, FamilyInstance,
    FilteredElementCollector, GraphicsStyleType, Line, Transaction, ViewPlan, XYZ,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from firealarm.loops import START, line_between, plan_loops

M_PER_FOOT = 0.3048
STYLE = u"FA Loop %d"
_STYLE_NAME = re.compile(r"^FA Loop (\d+)$")
COLOURS = [(255, 0, 0), (0, 0, 255), (0, 153, 0), (255, 0, 255), (255, 128, 0),
           (0, 153, 153), (128, 0, 255), (153, 76, 0)]
LINE_WEIGHT = 3
MIN_LINE = 0.005            # m; Revit refuses lines shorter than about 0.8 mm
_PANEL = re.compile(r"\b(PANEL|FACP|CIE)\b")


# ---------------------------------------------------------------- helpers

def id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _point(element):
    return getattr(getattr(element, "Location", None), "Point", None)


def is_plan(view):
    """Floor, ceiling, structural or area plan (not a template)."""
    return isinstance(view, ViewPlan) and not view.IsTemplate


def is_device(element):
    """A family instance placed at a point."""
    return isinstance(element, FamilyInstance) and _point(element) is not None


def label(element):
    """'Family : Type' of a family instance."""
    try:
        family = element.Symbol.FamilyName
    except Exception:
        family = ""
    try:
        p = element.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        name = p.AsString() if p is not None else ""
    except Exception:
        name = ""
    return u" : ".join(x for x in (family, name) if x) or u"id %s" % id_int(element.Id)


def is_panel(element):
    """Electrical equipment, or a family or type named ...PANEL, FACP, CIE."""
    try:
        if id_int(element.Category.Id) == int(BuiltInCategory.OST_ElectricalEquipment):
            return True
    except Exception:
        pass
    return bool(_PANEL.search(label(element).upper()))


# ---------------------------------------------------------------- devices

def view_devices(doc, view):
    """Fire alarm devices shown in the view, not the parts nested in
    another family."""
    found = []
    for element in FilteredElementCollector(doc, view.Id) \
            .OfCategory(BuiltInCategory.OST_FireAlarmDevices).OfClass(FamilyInstance):
        if element.SuperComponent is None and _point(element) is not None:
            found.append(element)
    return found


def selected_devices(uidoc):
    doc = uidoc.Document
    elements = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    return [e for e in elements if e is not None and is_device(e)]


class _LoopDeviceFilter(ISelectionFilter):
    __namespace__ = "FireAlarmDetectors"    # needed by the CPython engine

    def AllowElement(self, element):
        return is_device(element)

    def AllowReference(self, reference, position):
        return False


def pick_devices(uidoc):
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _LoopDeviceFilter(), "Select the devices, then click Finish")
    except OperationCanceledException:
        return []
    doc = uidoc.Document
    return [doc.GetElement(r.ElementId) for r in refs]


def pick_start(uidoc):
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.Element, _LoopDeviceFilter(),
            "Click the panel, or the device where the loop starts")
    except OperationCanceledException:
        return None
    return uidoc.Document.GetElement(ref.ElementId)


# ---------------------------------------------------------------- lines

def loop_lines(doc, view):
    """{loop number: [ElementId]} of the FA Loop lines drawn in the view."""
    found = {}
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        try:
            if id_int(curve.OwnerViewId) != id_int(view.Id):
                continue
            match = _STYLE_NAME.match(curve.LineStyle.Name)
        except Exception:
            continue
        if match:
            found.setdefault(int(match.group(1)), []).append(curve.Id)
    return found


def _style(doc, number):
    """The FA Loop <number> line style, made the first time."""
    categories = doc.Settings.Categories
    lines = categories.get_Item(BuiltInCategory.OST_Lines)
    name = STYLE % number
    if lines.SubCategories.Contains(name):
        sub = lines.SubCategories.get_Item(name)
    else:
        sub = categories.NewSubcategory(lines, name)
        r, g, b = COLOURS[(number - 1) % len(COLOURS)]
        sub.LineColor = Color(r, g, b)
        sub.SetLineWeight(LINE_WEIGHT, GraphicsStyleType.Projection)
    return sub.GetGraphicsStyle(GraphicsStyleType.Projection)


def _box(element, view):
    """(x0, y0, x1, y1) of the element as shown in the view (m), or None."""
    try:
        box = element.get_BoundingBox(view)
    except Exception:
        box = None
    if box is None:
        return None
    return (box.Min.X * M_PER_FOOT, box.Min.Y * M_PER_FOOT,
            box.Max.X * M_PER_FOOT, box.Max.Y * M_PER_FOOT)


def _detail_line(doc, view, a, b, z):
    error = None
    for height in (z, 0.0):
        try:
            return doc.Create.NewDetailCurve(view, Line.CreateBound(
                XYZ(a[0] / M_PER_FOOT, a[1] / M_PER_FOOT, height),
                XYZ(b[0] / M_PER_FOOT, b[1] / M_PER_FOOT, height)))
        except Exception as err:
            error = err
    raise error


class LoopResult(object):
    def __init__(self, number, devices, length):
        self.number = number        # FA Loop <number>
        self.devices = devices      # how many devices
        self.length = length        # m, centre to centre, back to the start
        self.lines = 0              # detail lines drawn
        self.failed = []            # messages


def draw_loops(doc, view, devices, start, max_devices, gap_mm, first_number=1, old=()):
    """Plan the loops of `devices` from `start` (an element; one of the
    devices, or the panel) and draw them in `view` as detail lines, one
    undo. `old`: ids of loop lines to delete. Returns [LoopResult]."""
    points = [(p.X * M_PER_FOOT, p.Y * M_PER_FOOT) for p in (_point(d) for d in devices)]
    ids = [id_int(d.Id) for d in devices]
    start_xy = _point(start)
    start_xy = (start_xy.X * M_PER_FOOT, start_xy.Y * M_PER_FOOT)
    first = ids.index(id_int(start.Id)) if id_int(start.Id) in ids else None
    loops = plan_loops(points, first if first is not None else start_xy, max_devices)

    boxes = [_box(d, view) for d in devices]
    start_box = _box(start, view)
    gap = gap_mm / 1000.0 * view.Scale                  # m in the model
    level = getattr(view, "GenLevel", None)
    z = level.ProjectElevation if level is not None else 0.0

    def where(stop):
        return (start_xy, start_box) if stop == START else (points[stop], boxes[stop])

    results = []
    t = Transaction(doc, "Draw FA Loop")
    t.Start()
    try:
        if old:
            doc.Delete(List[ElementId](list(old)))
        for number, loop in enumerate(loops, first_number):
            result = LoopResult(number, len(loop.devices), loop.length)
            results.append(result)
            style = _style(doc, number)
            for a, b in loop.segments():
                (pa, box_a), (pb, box_b) = where(a), where(b)
                line = line_between(pa, pb, box_a, box_b, gap)
                if line is None or math.hypot(line[1][0] - line[0][0],
                                              line[1][1] - line[0][1]) < MIN_LINE:
                    continue
                try:
                    curve = _detail_line(doc, view, line[0], line[1], z)
                    curve.LineStyle = style
                    result.lines += 1
                except Exception as err:
                    result.failed.append(u"%s" % err)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return results
