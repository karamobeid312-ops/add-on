# -*- coding: utf-8 -*-
"""Revit side of Address Devices: the loops drawn in the plans (FA Loop n
and FA Sounder Loop n lines) read back device by device from their lines
(firealarm.loop_order), and the order a loop's floors are counted in.

A loop's route starts where its lines end at a panel shown in the plan,
else at the line ends at nothing (where the panel is when it is not a
fire alarm family), else, drawn from a device, at the device nearest the
main panel. Panels are fire alarm devices or electrical equipment named
FACP, MFACP, ...CONTROL PANEL, as for FA Riser.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

from Autodesk.Revit.DB import BuiltInCategory, FamilyInstance, FilteredElementCollector, ViewPlan

from firealarm.loop_order import route_order
from firealarm.revit_loop import (device_reach, id_int, label, level_of, loop_curves,
                                  model_levels, view_devices)
from firealarm.riser_symbols import is_panel_name

MM_PER_FOOT = 304.8


class DrawnLoop(object):
    """The lines of one loop in one plan, and the devices they pass."""

    def __init__(self, number, kind, view):
        self.number = number
        self.kind = kind            # DETECTION / SOUNDER
        self.view = view
        self.devices = []           # in route order from the start
        self.loose = []             # at its lines, but not on the route from the start
        self.closed = False         # the lines go round and back to the start
        self.from_device = False    # it starts at a device, not at the panel
        self.start = None           # that device (counted on the first loop from it only)


def _xy(element):
    p = element.Location.Point
    return p.X, p.Y


def _panels(doc, view, shown):
    """Fire alarm panels shown in the view."""
    found = [d for d in shown if is_panel_name(label(d))]
    for element in FilteredElementCollector(doc, view.Id) \
            .OfCategory(BuiltInCategory.OST_ElectricalEquipment).OfClass(FamilyInstance):
        if getattr(element.Location, "Point", None) is not None and is_panel_name(label(element)):
            found.append(element)
    return found


def _segments(curves):
    found = []
    for curve in curves:
        try:
            geometry = curve.GeometryCurve
            a, b = geometry.GetEndPoint(0), geometry.GetEndPoint(1)
        except Exception:
            continue
        found.append(((a.X, a.Y), (b.X, b.Y)))
    return found


def read_loops(doc, gap_mm, panel=None, view=None):
    """[DrawnLoop] of the loops drawn in `view`, or in every plan (None).
    gap_mm: the loop line gap of FA Settings; panel: the main panel (an
    element) or None."""
    by_view = {}
    for number, owner, curve, kind in loop_curves(doc):
        if view is not None and owner != id_int(view.Id):
            continue
        by_view.setdefault(owner, (curve.OwnerViewId, {}))[1] \
            .setdefault((number, kind), []).append(curve)
    near = _xy(panel) if panel is not None else None
    found = []
    for owner in sorted(by_view):
        view_id, lines = by_view[owner]
        plan = doc.GetElement(view_id)
        if not isinstance(plan, ViewPlan):
            continue
        gap = gap_mm / MM_PER_FOOT * plan.Scale
        shown = view_devices(doc, plan)
        devices = [d for d in shown if not is_panel_name(label(d))]
        reach = [_xy(d) + (device_reach(d, plan, gap),) for d in devices]
        panels = [_xy(p) + (device_reach(p, plan, gap),) for p in _panels(doc, plan, shown)]
        routes = {}
        for key in sorted(lines):
            segments = _segments(lines[key])
            routes[key] = (segments, route_order(segments, reach, panels, near))
        # loops drawn from one device all start and end at it: the device
        # on several of them
        on = {}
        for key, (_, route) in routes.items():
            if route.from_device:
                for k in set(route.order) | set(route.loose):
                    on[k] = on.get(k, 0) + 1
        for key, (segments, route) in routes.items():
            shared = [k for k in route.order + route.loose if on.get(k, 0) > 1]
            if route.from_device and shared and route.order[:1] != shared[:1]:
                routes[key] = (segments, route_order(segments, reach, panels, shared[0]))
        for number, kind in sorted(routes):
            route = routes[(number, kind)][1]
            loop = DrawnLoop(number, kind, plan)
            loop.devices = [devices[k] for k in route.order]
            loop.loose = [devices[k] for k in route.loose]
            loop.closed = route.closed
            loop.from_device = route.from_device
            loop.start = loop.devices[0] if route.from_device and loop.devices else None
            found.append(loop)
    _shared_starts(found)
    return found


def _shared_starts(loops):
    """Loops drawn from a device all start and end at it (Draw FA Loop,
    more devices than one loop takes): it is counted on the first loop
    only, the one with the lowest number."""
    first = {}
    for loop in loops:
        if loop.from_device and loop.devices:
            key = (id_int(loop.view.Id), id_int(loop.devices[0].Id))
            first[key] = min(first.get(key, loop.number), loop.number)
    for loop in loops:
        if loop.from_device and loop.devices:
            key = (id_int(loop.view.Id), id_int(loop.devices[0].Id))
            if first[key] != loop.number:
                loop.devices = loop.devices[1:]


def panel_elevation(doc, panel):
    """Elevation of the main panel's floor (ft); 0 without a panel."""
    if panel is not None:
        try:
            return level_of(doc, panel, model_levels(doc)).ProjectElevation
        except Exception:
            pass
    return 0.0


def counting_order(parts, elevation):
    """A loop's parts (DrawnLoop, one per plan) in the order their devices
    are counted: the floor furthest from the panel's floor (at
    `elevation`) first, as on the riser."""
    def key(part):
        level = getattr(part.view, "GenLevel", None)
        z = level.ProjectElevation if level is not None else 0.0
        return (-abs(z - elevation), -z, part.view.Name)
    return sorted(parts, key=key)
