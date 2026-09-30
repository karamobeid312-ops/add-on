# -*- coding: utf-8 -*-
"""Revit side of Draw FA Loop: fire alarm devices of a plan view ->
loops (firealarm.loops) -> detail lines in that view.

Every loop leaves the start (the panel, or the device clicked first),
passes each of its devices once and comes back. Lines are square (at
right angles, along the grid the devices are laid out on) or straight.
Each loop has its own line style, FA Loop 1, FA Loop 2... (subcategories
of Lines, made with a colour the first time). Lines stop at the edge of
each device.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math
import re

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Color, CurveElement, ElementId, FamilyInstance,
    FilteredElementCollector, GraphicsStyleType, Level, Line, Transaction, ViewPlan, XYZ,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from firealarm.addresses import DETECTION, SOUNDER
from firealarm.loops import grid_angle, loop_lines, loop_numbers, plan_loops
from firealarm.riser_symbols import is_panel_name

M_PER_FOOT = 0.3048
STYLES = {DETECTION: u"FA Loop %d", SOUNDER: u"FA Sounder Loop %d"}
_STYLE_NAME = re.compile(r"^FA (Sounder )?Loop (\d+)$")
COLOURS = [(255, 0, 0), (0, 0, 255), (0, 153, 0), (255, 0, 255), (255, 128, 0),
           (0, 153, 153), (128, 0, 255), (153, 76, 0)]
LINE_WEIGHT = 3
MIN_LINE = 0.005            # m; Revit refuses lines shorter than about 0.8 mm
REACH_TOLERANCE = 0.1      # ft round a device's box in which a loop line may end
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
    """Electrical equipment, or a family or type named ...PANEL, FACP,
    MFACP, CIE."""
    try:
        if id_int(element.Category.Id) == int(BuiltInCategory.OST_ElectricalEquipment):
            return True
    except Exception:
        pass
    name = label(element)
    return bool(_PANEL.search(name.upper())) or is_panel_name(name)


# ---------------------------------------------------------------- floors

def model_levels(doc):
    """The levels of the model, lowest first."""
    return sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.ProjectElevation)


def _schedule_level(element):
    try:
        p = element.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
        return p.AsElementId() if p is not None else None
    except Exception:
        return None


def level_of(doc, element, levels):
    """The element's level, schedule level, or the level at or below it."""
    for level_id in (getattr(element, "LevelId", None), _schedule_level(element)):
        if level_id is not None and id_int(level_id) != id_int(ElementId.InvalidElementId):
            level = doc.GetElement(level_id)
            if isinstance(level, Level):
                return level
    z = _point(element).Z
    below = [l for l in levels if l.ProjectElevation <= z + 0.01]
    return below[-1] if below else (levels[0] if levels else None)


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

def _loop_style(curve):
    """(loop number, kind) of a loop line, or None."""
    match = _STYLE_NAME.match(curve.LineStyle.Name)
    if not match:
        return None
    return int(match.group(2)), (SOUNDER if match.group(1) else DETECTION)


def loop_curves(doc):
    """[(loop number, owner view id (int), curve, kind)] of every FA Loop
    and FA Sounder Loop line."""
    found = []
    for curve in FilteredElementCollector(doc).OfClass(CurveElement):
        try:
            owner = id_int(curve.OwnerViewId)
            if owner == id_int(ElementId.InvalidElementId):
                continue
            style = _loop_style(curve)
        except Exception:
            continue
        if style:
            found.append((style[0], owner, curve, style[1]))
    return found


def loop_views(doc, kind=None):
    """{loop number: set(names of the views it is drawn in)}, of one kind
    of loop (DETECTION / SOUNDER) or of both."""
    found = {}
    names = {}
    for number, owner, curve, loop_kind in loop_curves(doc):
        if kind is not None and loop_kind != kind:
            continue
        if owner not in names:
            view = doc.GetElement(curve.OwnerViewId)
            names[owner] = view.Name if view is not None else "view %d" % owner
        found.setdefault(number, set()).add(names[owner])
    return found


def existing_loop_lines(doc, view, kind=None):
    """{loop number: [ElementId]} of the loop lines drawn in the view, of
    one kind of loop or of both."""
    found = {}
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        try:
            if id_int(curve.OwnerViewId) != id_int(view.Id):
                continue
            style = _loop_style(curve)
        except Exception:
            continue
        if style and (kind is None or style[1] == kind):
            found.setdefault(style[0], []).append(curve.Id)
    return found


def _style(doc, number, kind=DETECTION):
    """The FA Loop <number> (or FA Sounder Loop <number>) line style, made
    the first time."""
    categories = doc.Settings.Categories
    lines = categories.get_Item(BuiltInCategory.OST_Lines)
    name = STYLES[kind] % number
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


def device_reach(element, view, gap):
    """How far from the device's centre a loop line ending at it can stop
    (ft): half its box's diagonal in the view, or the line gap (ft in the
    model) when more, and a little over."""
    p = _point(element)
    size = gap
    try:
        box = element.get_BoundingBox(view)
    except Exception:
        box = None
    if box is not None:
        size = max(size, math.hypot(max(p.X - box.Min.X, box.Max.X - p.X),
                                    max(p.Y - box.Min.Y, box.Max.Y - p.Y)))
    return size + REACH_TOLERANCE


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


def _band(boxes, gap):
    """How far off a row or column a device can be and still be on it:
    half the size of a typical device (m)."""
    sizes = sorted(min(b[2] - b[0], b[3] - b[1]) / 2 for b in boxes if b is not None)
    typical = sizes[len(sizes) // 2] if sizes else 0.0
    return max(typical, gap, 0.05)


class Plan(object):
    """The loops of `devices` from `start` (an element; one of the devices,
    or the panel), as Draw FA Loop routes them: loops (firealarm.loops.Loop,
    their devices in route order as indices into `devices`) and what
    drawing them needs."""

    def __init__(self, view, devices, start, max_devices, gap_mm, square=True):
        self.devices = devices
        self.square = square
        self.points = [(p.X * M_PER_FOOT, p.Y * M_PER_FOOT) for p in (_point(d) for d in devices)]
        ids = [id_int(d.Id) for d in devices]
        start_xy = _point(start)
        self.start_xy = (start_xy.X * M_PER_FOOT, start_xy.Y * M_PER_FOOT)
        first = ids.index(id_int(start.Id)) if id_int(start.Id) in ids else None
        self.boxes = [_box(d, view) for d in devices]
        self.start_box = _box(start, view)
        self.gap = gap_mm / 1000.0 * view.Scale                 # m in the model
        right = view.RightDirection
        self.angle = grid_angle(self.points, math.atan2(right.Y, right.X)) if square else 0.0
        self.loops = plan_loops(self.points, first if first is not None else self.start_xy,
                                max_devices, square, self.angle, _band(self.boxes, self.gap))

    def routes(self):
        """[[devices of a loop in route order]]."""
        return [[self.devices[i] for i in loop.devices] for loop in self.loops]


def draw_loops(doc, view, devices, start, max_devices, gap_mm, numbers=None, old=(),
               square=True, kind=DETECTION):
    """Plan the loops of `devices` from `start` (an element; one of the
    devices, or the panel) and draw them in `view` as detail lines, one
    undo. numbers: the loop numbers to give them (loops.loop_numbers);
    `old`: ids of loop lines to delete. square: lines at right angles
    along the devices' grid. Returns [LoopResult]."""
    plan = Plan(view, devices, start, max_devices, gap_mm, square)
    level = getattr(view, "GenLevel", None)
    z = level.ProjectElevation if level is not None else 0.0

    results = []
    t = Transaction(doc, "Draw FA Loop")
    t.Start()
    try:
        if old:
            doc.Delete(List[ElementId](list(old)))
        drawn = []                          # square lines so far, kept clear of
        numbers = list(numbers or [])
        numbers += loop_numbers(len(plan.loops) - len(numbers), numbers)
        for number, loop in zip(numbers, plan.loops):
            result = LoopResult(number, len(loop.devices), loop.length)
            results.append(result)
            style = _style(doc, number, kind)
            for line in loop_lines(loop, plan.points, plan.start_xy, plan.boxes, plan.start_box,
                                   plan.gap, square, plan.angle, drawn):
                if math.hypot(line[1][0] - line[0][0], line[1][1] - line[0][1]) < MIN_LINE:
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
