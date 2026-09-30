# -*- coding: utf-8 -*-
"""Revit side of FA Riser: fire alarm devices, their floors and the loops
drawn with Draw FA Loop -> riser diagram in a new drafting view.

A device is on FA Loop n when an FA Loop n line of a plan ends at it
(loop lines stop at the edge of each device). Its floor is its level
(or schedule level, or the level below it). Its symbol comes from its
'FA Symbol' parameter, else the one chosen in FA Settings, else a guess
from the family and type name (firealarm.riser_symbols).

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, FamilyInstance, FilteredElementCollector,
    Level, Transaction, ViewPlan,
)

from firealarm.revit_address import symbol_of
from firealarm.revit_loop import id_int, label, loop_curves
from firealarm.riser import Segment, riser_layout
from firealarm.riser_symbols import is_panel_name
from sld.revit_sld import render

VIEW_NAME = "FA Riser Diagram"
MM_PER_FOOT = 304.8
TOLERANCE = 0.1         # ft round a device's box in which a loop line may end


def _point(element):
    return getattr(getattr(element, "Location", None), "Point", None)


def _instances(doc, bic):
    found = []
    for element in FilteredElementCollector(doc).OfCategory(bic).OfClass(FamilyInstance):
        if element.SuperComponent is None and _point(element) is not None:
            found.append(element)
    return found


def devices_and_panels(doc):
    """(fire alarm devices, fire alarm panels) placed in the model."""
    devices, panels = [], []
    for element in _instances(doc, BuiltInCategory.OST_FireAlarmDevices):
        (panels if is_panel_name(label(element)) else devices).append(element)
    for element in _instances(doc, BuiltInCategory.OST_ElectricalEquipment):
        if is_panel_name(label(element)):
            panels.append(element)
    return devices, panels


def type_names(doc):
    """'Family : Type' of the fire alarm devices placed, sorted."""
    return sorted(set(label(d) for d in devices_and_panels(doc)[0]))


# ---------------------------------------------------------------- floors

def _levels(doc):
    return sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.ProjectElevation)


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


def _schedule_level(element):
    try:
        p = element.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
        return p.AsElementId() if p is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------- loops

def loop_of_devices(doc, devices, gap_mm):
    """({device id (int): loop number}, [device ids on two loops]): a
    device is on a loop when one of the loop's lines ends at it, that is
    within half its box's diagonal (or the line gap) of its centre; the
    nearest device takes the end."""
    wanted = set(id_int(d.Id) for d in devices)
    by_view = {}
    for number, owner, curve, _ in loop_curves(doc):
        by_view.setdefault(owner, (curve.OwnerViewId, []))[1].append((number, curve))
    found, twice = {}, set()
    for owner, (view_id, lines) in by_view.items():
        view = doc.GetElement(view_id)
        if not isinstance(view, ViewPlan):
            continue
        gap = gap_mm / MM_PER_FOOT * view.Scale
        reach = []                          # (device id, x, y, how far a line end can be)
        for element in FilteredElementCollector(doc, view.Id) \
                .OfCategory(BuiltInCategory.OST_FireAlarmDevices).OfClass(FamilyInstance):
            if id_int(element.Id) not in wanted:
                continue
            p = _point(element)
            box = element.get_BoundingBox(view)
            size = gap
            if box is not None:
                size = max(size, math.hypot(max(p.X - box.Min.X, box.Max.X - p.X),
                                            max(p.Y - box.Min.Y, box.Max.Y - p.Y)))
            reach.append((id_int(element.Id), p.X, p.Y, size + TOLERANCE))
        for number, curve in lines:
            try:
                ends = [curve.GeometryCurve.GetEndPoint(0), curve.GeometryCurve.GetEndPoint(1)]
            except Exception:
                continue
            for end in ends:
                near = [(math.hypot(end.X - x, end.Y - y), element_id)
                        for element_id, x, y, r in reach if math.hypot(end.X - x, end.Y - y) <= r]
                if not near:
                    continue
                element_id = min(near)[1]
                if found.get(element_id, number) != number:
                    twice.add(element_id)
                found.setdefault(element_id, number)
    return found, sorted(twice)


# ---------------------------------------------------------------- riser

class RiserRun(object):
    """What FA Riser read and drew, for the summary."""

    def __init__(self):
        self.riser = None
        self.view_name = ""
        self.panel = ""             # 'Family : Type' of the main panel, '' when none found
        self.panel_floor = ""
        self.off_loop = {}          # floor name -> devices no loop line reaches
        self.two_loops = 0          # devices at the ends of two loops' lines
        self.symbols = {}           # 'Family : Type' -> symbol code


def _main_panel(panels):
    main = [p for p in panels if "MAIN" in label(p).upper() or "MFACP" in label(p).upper()]
    return (main or panels or [None])[0]


def _room(element):
    try:
        room = element.Room
    except Exception:
        room = None
    if room is None:
        return ""
    try:
        name = room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or ""
        number = room.get_Parameter(BuiltInParameter.ROOM_NUMBER).AsString() or ""
    except Exception:
        return ""
    return u"%s (%s)" % (name, number) if number else name


def generate(doc, chosen, gap_mm, max_devices):
    """Read the model and draw the riser in a new drafting view. chosen:
    {'Family : Type': symbol code} from FA Settings. Returns (view or
    None, RiserRun)."""
    run = RiserRun()
    devices, panels = devices_and_panels(doc)
    levels = _levels(doc)
    if not levels:
        return None, run
    floor_of = dict((id_int(d.Id), level_of(doc, d, levels)) for d in devices)
    loop_of, twice = loop_of_devices(doc, devices, gap_mm)
    run.two_loops = len(twice)

    counts = {}
    used_levels = set()
    for d in devices:
        level = floor_of[id_int(d.Id)]
        if level is None:
            continue
        used_levels.add(id_int(level.Id))
        name = label(d)
        code = run.symbols.get(name) or symbol_of(d, chosen)
        run.symbols[name] = code
        number = loop_of.get(id_int(d.Id))
        if number is None:
            run.off_loop[level.Name] = run.off_loop.get(level.Name, 0) + 1
            continue
        per_type = counts.setdefault((number, level.Name), {})
        per_type[code] = per_type.get(code, 0) + 1

    panel = _main_panel(panels)
    if panel is not None:
        run.panel = label(panel)
        panel_level = level_of(doc, panel, levels)
    else:
        used = [l for l in levels if id_int(l.Id) in used_levels]
        panel_level = min(used or levels, key=lambda l: abs(l.ProjectElevation))
    run.panel_floor = panel_level.Name
    used_levels.add(id_int(panel_level.Id))

    floors = [(l.Name, l.ProjectElevation) for l in levels if id_int(l.Id) in used_levels]
    segments = [Segment(number, floor, per_type) for (number, floor), per_type in counts.items()]
    run.riser = riser_layout(floors, segments, panel_level.Name,
                             _room(panel) if panel is not None else "", max_devices)
    if not run.riser.loops:
        return None, run

    t = Transaction(doc, "FA Riser Diagram")
    t.Start()
    try:
        view = render(doc, run.riser.drawing, VIEW_NAME)
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    run.view_name = view.Name
    return view, run
