# -*- coding: utf-8 -*-
"""Circuiting the FCU outlets: each outlet gets its own power circuit on
the panel picked, a home-run wire (free end, so Revit draws its arrow)
pointing towards the panel, and a wire tag ("Y9 TO LDB-B/1-G" with the
office tag family) in the floor's plan."""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, FamilySymbol, FilteredElementCollector,
    IndependentTag, Reference, TagOrientation, Transaction, ViewPlan, ViewType, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType, Wire, WireType, \
    WiringType

from fcupower.revit_fcu import FEET, id_int

HOME_RUN = 0.8 / FEET           # length of the home-run wire towards the panel
BOW = 0.15 / FEET               # how far the arc's middle is off the straight line
TAG_UP = 0.6 / FEET             # tag head above the wire's free end


def _text(element, bip):
    try:
        p = element.get_Parameter(bip)
        return (p.AsString() or u"") if p is not None else u""
    except Exception:
        return u""


def panels(doc):
    """{panel name: element} of the electrical equipment."""
    found = {}
    for e in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
            .WhereElementIsNotElementType():
        name = (_text(e, BuiltInParameter.RBS_ELEC_PANEL_NAME) or u"").strip()
        if name:
            found[name] = e
    return found


def wire_types(doc):
    """({name: WireType}, the name used most by the wires of the model)."""
    types = {}
    for t in FilteredElementCollector(doc).OfClass(WireType):
        name = _text(t, BuiltInParameter.SYMBOL_NAME_PARAM) or getattr(t, "Name", u"") or u"Wire"
        types[name] = t
    counts = {}
    for w in FilteredElementCollector(doc).OfClass(Wire):
        counts[id_int(w.GetTypeId())] = counts.get(id_int(w.GetTypeId()), 0) + 1
    best = max(types, key=lambda n: counts.get(id_int(types[n].Id), 0)) if types else None
    return types, best


def tag_types(doc):
    """({'Family : Type': symbol} of the wire tags, the one used most)."""
    types = {}
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol) \
            .OfCategory(BuiltInCategory.OST_WireTags):
        name = _text(s, BuiltInParameter.SYMBOL_NAME_PARAM)
        types[u"%s : %s" % (s.FamilyName, name)] = s
    counts = {}
    for tag in FilteredElementCollector(doc).OfClass(IndependentTag):
        key = id_int(tag.GetTypeId())
        counts[key] = counts.get(key, 0) + 1
    best = max(types, key=lambda n: counts.get(id_int(types[n].Id), 0)) if types else None
    return types, best


def _power_systems(element):
    try:
        systems = element.MEPModel.GetElectricalSystems()
    except Exception:
        try:
            systems = element.MEPModel.ElectricalSystems
        except Exception:
            return []
    try:
        return [s for s in systems if s.SystemType == ElectricalSystemType.PowerCircuit]
    except Exception:
        return []


def panel_name(element):
    """Name of the panel the outlet's circuit is on, or ''."""
    for system in _power_systems(element):
        try:
            if system.BaseEquipment is not None:
                return (_text(system.BaseEquipment, BuiltInParameter.RBS_ELEC_PANEL_NAME) or u"").strip()
        except Exception:
            pass
    return u""


def wired(element):
    """True when a wire is connected to the outlet."""
    connector = _connector(element)
    if connector is None:
        return False
    try:
        for ref in connector.AllRefs:
            if isinstance(ref.Owner, Wire):
                return True
    except Exception:
        pass
    return False


def circuited(element):
    """True when the outlet is already on a power circuit."""
    try:
        systems = element.MEPModel.GetElectricalSystems()
    except Exception:
        try:
            systems = element.MEPModel.ElectricalSystems
        except Exception:
            return False
    try:
        return any(s.SystemType == ElectricalSystemType.PowerCircuit for s in systems)
    except Exception:
        return False


def plan_of(doc, z):
    """The plan to draw the wire of an outlet at height z in: the active
    view when it is a plan, else a plan (floor plan first) of the highest
    level at or below z."""
    view = doc.ActiveView
    if _is_plan(view):
        return view
    levels = [v.GenLevel for v in FilteredElementCollector(doc).OfClass(ViewPlan)
              if _is_plan(v)]
    below = [l for l in levels if l.ProjectElevation <= z + 0.05]
    if not below:
        return None
    floor = max(l.ProjectElevation for l in below)
    plans = [v for v in FilteredElementCollector(doc).OfClass(ViewPlan)
             if _is_plan(v) and abs(v.GenLevel.ProjectElevation - floor) < 0.01]
    plans.sort(key=lambda v: (v.ViewType != ViewType.FloorPlan, v.Name))
    return plans[0] if plans else None


def _is_plan(view):
    try:
        return isinstance(view, ViewPlan) and not view.IsTemplate and view.GenLevel is not None
    except Exception:
        return False


def _connector(element):
    try:
        from Autodesk.Revit.DB import Domain
        for c in element.MEPModel.ConnectorManager.Connectors:
            if c.Domain == Domain.DomainElectrical:
                return c
    except Exception:
        pass
    return None


def _location(element):
    loc = element.Location
    point = getattr(loc, "Point", None)
    if point is not None:
        return point
    box = element.get_BoundingBox(None)
    return box.Min.Add(box.Max).Multiply(0.5) if box is not None else None


def _home_run_points(start, panel_point):
    dx, dy = panel_point.X - start.X, panel_point.Y - start.Y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    end = XYZ(start.X + ux * HOME_RUN, start.Y + uy * HOME_RUN, start.Z)
    mid = XYZ(start.X + ux * HOME_RUN / 2 - uy * BOW, start.Y + uy * HOME_RUN / 2 + ux * BOW, start.Z)
    return [start, mid, end]


def _keep_short(wire, outlet, points):
    """Revit runs a new wire of a circuited outlet to its panel: cut it
    back to a short home run (its far end free, so the arrow shows)."""
    outlet_id = id_int(outlet.Id)
    for c in wire.ConnectorManager.Connectors:
        for ref in list(c.AllRefs):
            try:
                if id_int(ref.Owner.Id) != outlet_id:
                    c.DisconnectFrom(ref)
            except Exception:
                pass
    while wire.NumberOfVertices > len(points):
        wire.RemoveVertex(wire.NumberOfVertices - 2)
    while wire.NumberOfVertices < len(points):
        wire.InsertVertex(wire.NumberOfVertices - 1, points[wire.NumberOfVertices - 1])
    far = wire.GetVertex(wire.NumberOfVertices - 1).DistanceTo(points[-1])
    if far > 0.01:
        for i in range(len(points) - 1, 0, -1):
            wire.SetVertex(i, XYZ(points[i].X, points[i].Y, wire.GetVertex(i).Z))


def circuit_and_wire(doc, outlets, panel, wire_type, tag_type, view_for):
    """One circuit per outlet on `panel`, then its home-run wire and tag in
    the plan view_for(outlet) gives (no wire when it gives None). One undo.
    Returns (circuits, wires, tags, [failures])."""
    from System.Collections.Generic import List
    made = wired = tagged = 0
    failed = []
    panel_point = _location(panel)
    t = Transaction(doc, "FCU outlets: circuit and wire")
    t.Start()
    try:
        if tag_type is not None and not tag_type.IsActive:
            tag_type.Activate()
            doc.Regenerate()
        for label, outlet in outlets:
            if not circuited(outlet):
                ids = List[ElementId]()
                ids.Add(outlet.Id)
                try:
                    try:
                        system = ElectricalSystem.Create(doc, ids, ElectricalSystemType.PowerCircuit)
                    except AttributeError:
                        system = doc.Create.NewElectricalSystem(ids, ElectricalSystemType.PowerCircuit)
                    system.SelectPanel(panel)
                except Exception as error:
                    failed.append(u"%s: circuit refused (%s)" % (label, _first_line(error)))
                    continue
                made += 1
            elif wired(outlet):
                continue        # circuited and wired already
            view = view_for(outlet)
            if wire_type is None:
                continue
            if view is None:
                failed.append(u"%s: circuited, but no plan view found for the wire" % label)
                continue
            doc.Regenerate()
            connector = _connector(outlet)
            if connector is None:
                failed.append(u"%s: no electrical connector for the wire" % label)
                continue
            points = _home_run_points(connector.Origin, panel_point or connector.Origin)
            try:
                # Revit adds the connector's origin as the start vertex itself
                wire = Wire.Create(doc, wire_type.Id, view.Id, WiringType.Arc,
                                   List[XYZ](points[1:]), connector, None)
            except Exception as error:
                failed.append(u"%s: wire refused (%s)" % (label, _first_line(error)))
                continue
            wired += 1
            doc.Regenerate()
            try:
                _keep_short(wire, outlet, points)
            except Exception as error:
                failed.append(u"%s: wire drawn but not shortened (%s)" % (label, _first_line(error)))
            if tag_type is None:
                continue
            end = points[-1]
            head = XYZ(end.X, end.Y + TAG_UP, end.Z)
            try:
                # no leader (user's choice): the tag sits just above the arrow end
                tag = IndependentTag.Create(doc, tag_type.Id, view.Id, Reference(wire), False,
                                            TagOrientation.Horizontal, head)
                try:
                    tag.TagHeadPosition = head
                except Exception:
                    pass
                tagged += 1
            except Exception as error:
                failed.append(u"%s: tag refused (%s)" % (label, _first_line(error)))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return made, wired, tagged, failed


def _first_line(error):
    text = (u"%s" % (getattr(error, "Message", None) or error)).strip()
    return text.splitlines()[0] if text else u"refused by Revit"
