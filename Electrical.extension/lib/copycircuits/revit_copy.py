# -*- coding: utf-8 -*-
"""Revit side: circuits of a floor read, and made again on its copies.

Circuits (ElectricalSystem) are read from the model; their elements on
the source floor are matched to their copies on each target floor by
family type and plan position (plan.match). New circuits are made with
ElectricalSystem.Create, put on their panel with SelectPanel, and given
the source circuit's writable parameters (load name, rating, wire type,
wire sizes, notes, shared parameters...). Wires drawn in the source
floor's plans are drawn again with Wire.Create in the target floor's
plan of the same kind, between the copies' connectors.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

from Autodesk.Revit.DB import (
    BuiltInParameter, ElementId, FailureProcessingResult, FailureSeverity, FamilyInstance,
    FilteredElementCollector, IFailuresPreprocessor, Level, StorageType, Transaction,
    ViewPlan, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, Wire
from System.Collections.Generic import List

from copycircuits import plan
from copycircuits.report import LevelResult, Made


def id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


_INVALID = id_int(ElementId.InvalidElementId)


# ---------------------------------------------------------------- levels

def levels(doc):
    """Levels of the model, lowest first."""
    found = list(FilteredElementCollector(doc).OfClass(Level))
    found.sort(key=lambda l: l.Elevation)
    return found


def level_key(element, depth=0):
    """Key of the element's level, or None."""
    if element is None or depth > 3:
        return None
    ids = []
    try:
        ids.append(element.LevelId)
    except Exception:
        pass
    for bip in (BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
                BuiltInParameter.FAMILY_LEVEL_PARAM):
        try:
            ids.append(element.get_Parameter(bip).AsElementId())
        except Exception:
            pass
    for level_id in ids:
        try:
            if level_id is not None and id_int(level_id) != _INVALID:
                return id_int(level_id)
        except Exception:
            pass
    return level_key(getattr(element, "SuperComponent", None), depth + 1)


def _point(element):
    try:
        return element.Location.Point
    except Exception:
        return None


def _type_key(element):
    try:
        return id_int(element.GetTypeId())
    except Exception:
        return None


def _item(element):
    p = _point(element)
    if p is None:
        return None
    return plan.Item(id_int(element.Id), _type_key(element), p.X, p.Y)


def _systems_of(element):
    """Circuits the element is on."""
    try:
        model = element.MEPModel
    except Exception:
        return []
    if model is None:
        return []
    for name in ("GetElectricalSystems", "GetAssignedElectricalSystems"):
        try:
            found = getattr(model, name)()
            if found is not None:
                return list(found)
        except Exception:
            pass
    for name in ("ElectricalSystems", "AssignedElectricalSystems"):
        try:
            found = getattr(model, name)
            if found is not None:
                return list(found)
        except Exception:
            pass
    return []


def _kind(system):
    return str(system.SystemType)


# ---------------------------------------------------------------- source

class Source(object):
    """The circuits of the source floor and their elements."""

    def __init__(self, level):
        self.level = level
        self.circuits = []          # [plan.Circuit]
        self.systems = {}           # circuit key -> ElectricalSystem
        self.elements = {}          # element key -> element (circuits' elements and panels)
        self.items = []             # [plan.Item] of those on the source floor


def read_source(doc, level, only=None):
    """Circuits with elements on `level`. only: element ids (ints) chosen in
    Revit: then just the circuits that are, or have, or are fed by one of them."""
    here = id_int(level.Id)
    source = Source(level)
    seen = set()
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        try:
            elements = list(system.Elements)
        except Exception:
            continue
        panel = system.BaseEquipment
        if only is not None:
            keys = set(id_int(e.Id) for e in elements) | {id_int(system.Id)}
            if panel is not None:
                keys.add(id_int(panel.Id))
            if not keys & only:
                continue
        on_floor = [e for e in elements if level_key(e) == here]
        if not on_floor:
            continue
        key = id_int(system.Id)
        panel_here = panel is not None and level_key(panel) == here
        try:
            slot = system.StartSlot
        except Exception:
            slot = 0
        source.circuits.append(plan.Circuit(
            key, _kind(system), [id_int(e.Id) for e in on_floor],
            panel=id_int(panel.Id) if panel is not None else None, panel_here=panel_here,
            slot=slot, panel_name=system.PanelName or "", number=system.CircuitNumber or ""))
        source.systems[key] = system
        for e in on_floor + ([panel] if panel_here else []):
            k = id_int(e.Id)
            source.elements[k] = e
            if k not in seen:
                seen.add(k)
                item = _item(e)
                if item is not None:
                    source.items.append(item)
    return source


# ---------------------------------------------------------------- target

class Target(object):
    def __init__(self, level):
        self.level = level
        self.elements = {}          # key -> element, of the source's family types
        self.items = []
        self.circuited = set()      # (key, kind) already on a circuit


def read_target(doc, level, type_keys):
    here = id_int(level.Id)
    target = Target(level)
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
        if _type_key(e) not in type_keys or level_key(e) != here:
            continue
        item = _item(e)
        if item is None:
            continue
        target.elements[item.key] = e
        target.items.append(item)
        for system in _systems_of(e):
            try:
                target.circuited.add((item.key, _kind(system)))
            except Exception:
                pass
    return target


# ---------------------------------------------------------------- parameters

FIRST = ("RBS_ELEC_CIRCUIT_WIRE_TYPE_PARAM", "RBS_ELEC_CIRCUIT_RATING_PARAM",
         "RBS_ELEC_CIRCUIT_FRAME_PARAM")
ID_PARAMS = ("RBS_ELEC_CIRCUIT_WIRE_TYPE_PARAM",)
SKIP = ("ALL_MODEL_MARK",)


def _builtin(names):
    found = set()
    for name in names:
        bip = getattr(BuiltInParameter, name, None)
        if bip is not None:
            found.add(int(bip))
    return found


def _bip(param):
    try:
        return int(param.Definition.BuiltInParameter)
    except Exception:
        return None


def _set_like(src, dst, ids_ok):
    """Give dst (a parameter) the value of src. True when it changed."""
    if dst is None or dst.IsReadOnly or not src.HasValue:
        return False
    kind = src.StorageType
    if kind != dst.StorageType:
        return False
    try:
        if kind == StorageType.String:
            value = src.AsString()
            if value is None or value == dst.AsString():
                return False
            return dst.Set(value)
        if kind == StorageType.Integer:
            value = src.AsInteger()
            return value != dst.AsInteger() and dst.Set(value)
        if kind == StorageType.Double:
            value = src.AsDouble()
            return abs(value - dst.AsDouble()) > 1e-9 and dst.Set(value)
        if kind == StorageType.ElementId and ids_ok:
            value = src.AsElementId()
            return id_int(value) != id_int(dst.AsElementId()) and dst.Set(value)
    except Exception:
        return False
    return False


def copy_parameters(src, dst):
    """Writable parameters of src given to dst: the wire type and rating
    first (Revit sizes the wires from them), then the others."""
    first, ids_ok, skip = _builtin(FIRST), _builtin(ID_PARAMS), _builtin(SKIP)
    params = [p for p in src.Parameters if not p.IsReadOnly]
    params.sort(key=lambda p: 0 if _bip(p) in first else 1)
    for p in params:
        bip = _bip(p)
        if bip in skip:
            continue
        try:
            other = dst.get_Parameter(p.GUID) if p.IsShared else dst.get_Parameter(p.Definition)
        except Exception:
            other = None
        _set_like(p, other, bip in ids_ok)


# ---------------------------------------------------------------- wires

def _connectors(element):
    try:
        manager = element.ConnectorManager if isinstance(element, Wire) \
            else element.MEPModel.ConnectorManager
        return list(manager.Connectors)
    except Exception:
        return []


def _vertices(wire):
    try:
        return [wire.GetVertex(i) for i in range(wire.NumberOfVertices)]
    except Exception:
        return []


def _end_links(wire):
    """[(owner key, connector id) or None] for the wire's start and end."""
    points = _vertices(wire)
    ends = [None, None]
    if len(points) < 2:
        return ends
    for c in _connectors(wire):
        try:
            refs = [r for r in c.AllRefs if id_int(r.Owner.Id) != id_int(wire.Id)]
        except Exception:
            refs = []
        if not refs:
            continue
        r = refs[0]
        try:
            at = c.Origin
            end = 0 if at.DistanceTo(points[0]) <= at.DistanceTo(points[-1]) else 1
        except Exception:
            continue
        ends[end] = (id_int(r.Owner.Id), r.Id)
    return ends


def _view_info(view, level_names):
    try:
        template = id_int(view.ViewTemplateId)
        template = None if template == _INVALID else template
    except Exception:
        template = None
    try:
        level = level_names.get(id_int(view.GenLevel.Id), "")
    except Exception:
        level = ""
    return plan.View(id_int(view.Id), view.Name, str(view.ViewType), level, template,
                     _type_key(view))


class Wires(object):
    """The source floor's wires and the plans to copy them to."""

    def __init__(self, doc, source_level):
        self.doc = doc
        self.elevation = source_level.Elevation
        self.level_names = dict((id_int(l.Id), l.Name) for l in levels(doc))
        self.views = {}
        self.infos = []
        for v in FilteredElementCollector(doc).OfClass(ViewPlan):
            try:
                if v.IsTemplate or v.GenLevel is None:
                    continue
            except Exception:
                continue
            self.views[id_int(v.Id)] = v
            self.infos.append(_view_info(v, self.level_names))
        here = id_int(source_level.Id)
        self.source = []            # [(wire, source view info)]
        for w in FilteredElementCollector(doc).OfClass(Wire):
            view = self.views.get(id_int(w.OwnerViewId))
            try:
                if view is None or id_int(view.GenLevel.Id) != here:
                    continue
            except Exception:
                continue
            self.source.append((w, _view_info(view, self.level_names)))

    def _existing(self, view):
        return list(FilteredElementCollector(self.doc, view.Id).OfClass(Wire))


def _connector_of(element, connector_id):
    for c in _connectors(element):
        try:
            if c.Id == connector_id:
                return c
        except Exception:
            pass
    return None


def _same_spot(points, other, tolerance):
    if len(points) != len(other):
        return False
    for a, b in zip(points, other):
        if abs(a.X - b.X) > tolerance or abs(a.Y - b.Y) > tolerance:
            return False
    return True


def _connected_as(wire, wanted):
    """The wire's ends are connected to the elements `wanted` names."""
    ends = _end_links(wire)
    for got, want in zip(ends, wanted):
        if want is not None and (got is None or got[0] != want):
            return False
    return True


def copy_wires(wires, copies, targets, level, tolerance, result):
    """Draw the source wires again on `level`, between the copies."""
    dz = level.Elevation - wires.elevation
    existing = {}
    for wire, info in wires.source:
        ends = _end_links(wire)
        if all(e is None for e in ends):
            continue                # not connected to anything: a drafting wire
        if any(e is not None and e[0] not in copies for e in ends):
            result.wires["not_copied"] += 1
            continue
        view_info = plan.target_view(info, wires.infos, level.Name)
        if view_info is None:
            result.wires["no_view"] += 1
            continue
        view = wires.views[view_info.key]
        conns = [None, None]
        wanted = [None, None]
        for i, e in enumerate(ends):
            if e is None:
                continue
            wanted[i] = copies[e[0]]
            conns[i] = _connector_of(targets[wanted[i]], e[1])
        if any(e is not None and c is None for e, c in zip(ends, conns)):
            result.wires["not_copied"] += 1
            continue
        points = [XYZ(p.X, p.Y, p.Z + dz) for p in _vertices(wire)]
        if view_info.key not in existing:
            existing[view_info.key] = wires._existing(view)
        there = None
        for other in existing[view_info.key]:
            if other.IsValidObject and _same_spot(points, _vertices(other), tolerance):
                there = other
                break
        if there is not None:
            if _connected_as(there, wanted):
                result.wires["kept"] += 1
                continue
            existing[view_info.key].remove(there)
            wires.doc.Delete(there.Id)
            result.wires["removed"] += 1
        try:
            new = Wire.Create(wires.doc, wire.GetTypeId(), view.Id, wire.WiringType,
                              List[XYZ](points), conns[0], conns[1])
        except Exception:
            result.wires["not_copied"] += 1
            continue
        copy_parameters(wire, new)
        result.wires["drawn"] += 1


# ---------------------------------------------------------------- making

class _Quiet(IFailuresPreprocessor):
    """Dismisses Revit's warnings, so the copy runs without a dialog each time."""
    __namespace__ = "ElectricalCopyCircuits"       # needed by the CPython engine

    def PreprocessFailures(self, accessor):
        for message in list(accessor.GetFailureMessages()):
            if message.GetSeverity() == FailureSeverity.Warning:
                accessor.DeleteWarning(message)
        return FailureProcessingResult.Continue


def _ids(elements):
    found = List[ElementId]()
    for e in elements:
        found.Add(e.Id)
    return found


def _new_circuit(doc, elements, system_type):
    ids = _ids(elements)
    try:
        return ElectricalSystem.Create(doc, ids, system_type)
    except AttributeError:
        return doc.Create.NewElectricalSystem(ids, system_type)


def _message(error):
    text = (u"%s" % (getattr(error, "Message", None) or error)).strip()
    return text.splitlines()[0] if text else u"refused by Revit"


def copy_to(doc, source, level, tolerance, wires=None):
    """Make the source circuits on `level`. Returns its LevelResult."""
    result = LevelResult(level.Name)
    type_keys = set(i.type_key for i in source.items)
    target = read_target(doc, level, type_keys)
    copies = plan.match(source.items, target.items, tolerance)
    jobs, result.skipped = plan.plan(source.circuits, copies, target.circuited)

    t = Transaction(doc, "Copy circuits to %s" % level.Name)
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(_Quiet())
    t.SetFailureHandlingOptions(options)
    t.Start()
    try:
        for job in jobs:
            src = source.systems[job.circuit.key]
            elements = [target.elements[k] for k in job.elements]
            try:
                system = _new_circuit(doc, elements, src.SystemType)
            except Exception as error:
                result.failed.append((job, _message(error)))
                continue
            if system is None:
                result.failed.append((job, u"refused by Revit"))
                continue
            panel_error = None
            if job.panel is not None:
                panel = target.elements[job.panel] if job.circuit.panel_here \
                    else src.BaseEquipment
                try:
                    system.SelectPanel(panel)
                except Exception as error:
                    panel_error = _message(error)
            copy_parameters(src, system)
            result.made.append(Made(job, system.Id, panel_error))
        if wires is not None:
            copy_wires(wires, copies, target.elements, level, tolerance, result)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    matched = set(copies.values())
    circuited = set(k for k, _ in target.circuited)
    result.left = [target.elements[i.key].Id for i in target.items
                   if i.key not in matched and i.key not in circuited]
    return result
