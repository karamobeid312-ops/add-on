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
    BuiltInCategory, BuiltInParameter, ElementId, FailureProcessingResult, FailureSeverity, FamilyInstance,
    FilteredElementCollector, IFailuresPreprocessor, Level, StorageType, Transaction,
    ViewPlan, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, Wire
from System.Collections.Generic import List

from copycircuits import placement as placing
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


def _family_key(element):
    try:
        return id_int(element.Symbol.Family.Id)
    except Exception:
        return None


def _item(element):
    p = _point(element)
    if p is None:
        return None
    try:
        flip = bool(element.Mirrored)
    except Exception:
        flip = False
    return plan.Item(id_int(element.Id), _type_key(element), p.X, p.Y, p.Z,
                     _family_key(element), flip, _facing(element))


def _facing(element):
    """(x, y) the element faces in plan (else its hand direction), or None."""
    for name in ("FacingOrientation", "HandOrientation"):
        try:
            v = getattr(element, name)
            length = (v.X ** 2 + v.Y ** 2) ** 0.5
            if length >= 0.5:
                return v.X / length, v.Y / length
        except Exception:
            pass
    return None


STOREY = 2.0 / 0.3048      # ft: levels nearer than this above a floor are not floors
                           # (SSL, ceiling levels)
BELOW = 0.3 / 0.3048       # ft: floor boxes and the like may sit this much below their floor


class Floor(object):
    """A level and the height of its storey. An element is on the floor when
    its Level is that level, or when it is in the storey: from just below
    the level up to just below the next floor (whatever level it was given)."""

    def __init__(self, level, all_levels):
        self.level = level
        self.key = id_int(level.Id)
        self.low = level.Elevation - BELOW
        above = [l.Elevation for l in all_levels if l.Elevation > level.Elevation + STOREY]
        self.high = (min(above) - BELOW) if above else None

    def has(self, element):
        """(on the floor, by height only)."""
        if level_key(element) == self.key:
            return True, False
        p = _point(element)
        if p is None:
            return False, False
        inside = p.Z >= self.low and (self.high is None or p.Z < self.high)
        return inside, inside


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
        self.by_height = 0          # of those, on the floor by height, not by their Level
        self.panels = {}            # panel key -> panel, of every circuit read


def read_source(doc, level, only=None):
    """Circuits with elements on `level`. only: element ids (ints) chosen in
    Revit: then just the circuits that are, or have, or are fed by one of them."""
    floor = Floor(level, levels(doc))
    source = Source(level)
    seen, odd = set(), set()
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
        on_floor = []
        for e in elements:
            inside, by_height = floor.has(e)
            if inside:
                on_floor.append(e)
                if by_height:
                    odd.add(id_int(e.Id))
        if not on_floor:
            continue
        key = id_int(system.Id)
        panel_here = panel is not None and floor.has(panel)[0]
        try:
            slot = system.StartSlot
        except Exception:
            slot = 0
        source.circuits.append(plan.Circuit(
            key, _kind(system), [id_int(e.Id) for e in on_floor],
            panel=id_int(panel.Id) if panel is not None else None, panel_here=panel_here,
            slot=slot, panel_name=system.PanelName or "", number=system.CircuitNumber or ""))
        source.systems[key] = system
        if panel is not None:
            source.panels[id_int(panel.Id)] = panel
        for e in on_floor + ([panel] if panel_here else []):
            k = id_int(e.Id)
            source.elements[k] = e
            if k not in seen:
                seen.add(k)
                item = _item(e)
                if item is not None:
                    source.items.append(item)
    source.by_height = len(odd)
    return source


# ---------------------------------------------------------------- target

class Target(object):
    def __init__(self, level):
        self.level = level
        self.elements = {}          # key -> element, of the source's family types
        self.items = []             # those that can be copies
        self.all_items = []         # with the source's own too (on the same floor)
        self.circuited = set()      # (key, kind) already on a circuit


def _member_of(element):
    """The circuits the element is on, not those it feeds (a panel's)."""
    found = []
    me = id_int(element.Id)
    for system in _systems_of(element):
        try:
            base = system.BaseEquipment
            if base is not None and id_int(base.Id) == me:
                continue
        except Exception:
            pass
        found.append(system)
    return found


def read_target(doc, level, type_keys, family_keys, exclude=()):
    """The elements on `level` of the source's family types or families.
    Those in `exclude` (the source's own, when it is the same floor) are not
    copies, but are kept in all_items, where panels are looked for."""
    floor = Floor(level, levels(doc))
    target = Target(level)
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
        if _type_key(e) not in type_keys and _family_key(e) not in family_keys:
            continue
        if not floor.has(e)[0]:
            continue
        item = _item(e)
        if item is None:
            continue
        target.elements[item.key] = e
        target.all_items.append(item)
        if item.key not in exclude:
            target.items.append(item)
        for system in _member_of(e):
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
        try:                        # the device it is on, not the circuit or another wire
            refs = [r for r in c.AllRefs if isinstance(r.Owner, FamilyInstance)]
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
        self.view_level = {}        # view key -> level key
        for key, v in self.views.items():
            self.view_level[key] = id_int(v.GenLevel.Id)
        self.infos_by_key = dict((i.key, i) for i in self.infos)
        here = id_int(source_level.Id)
        self.source = []            # [(wire, source view info)]
        self.all = []               # [(wire, view key)] of every wire in a plan
        for w in FilteredElementCollector(doc).OfClass(Wire):
            key = id_int(w.OwnerViewId)
            if key not in self.views:
                continue
            self.all.append((w, key))
            if self.view_level[key] == here:
                self.source.append((w, self.infos_by_key[key]))

        self.elevations = dict((id_int(l.Id), l.Elevation) for l in levels(doc))
        self.source_level = here

    def on_level(self, level, mine=()):
        """{view key: [wire]} of the wires already in the plans of the level and
        of the levels at its height (the other tower's own levels), but those
        in `mine` (the source wires copied)."""
        found = {}
        for w, key in self.all:
            height = self.elevations.get(self.view_level[key])
            if height is None or abs(height - level.Elevation) > 0.01:
                continue
            if not w.IsValidObject or id_int(w.Id) in mine:
                continue
            found.setdefault(key, []).append(w)
        return found

    def add(self, wire, view_key):
        self.all.append((wire, view_key))


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


def _find_there(existing, view_keys, points, tolerance, claimed=()):
    """(wire, view key) of a wire already at the spot in one of the views,
    not claimed by another source wire."""
    for key in view_keys:
        for other in existing.get(key, ()):
            if id_int(other.Id) in claimed:
                continue
            if other.IsValidObject and _same_spot(points, _vertices(other), tolerance):
                return other, key
    return None, None


def _snapped(points, conns):
    """The points with the wire's ends on its connectors."""
    points = list(points)
    for i, c in ((0, conns[0]), (-1, conns[1])):
        if c is not None:
            o = c.Origin
            points[i] = XYZ(o.X, o.Y, points[i].Z)
    return points


def _unwired(result, targets, wanted):
    for k in wanted:
        if k is not None and k in targets and targets[k].Id not in result.unwired:
            result.unwired.append(targets[k].Id)


def copy_wires(wires, copies, targets, level, tolerance, result, source, circuited,
               where=placing.SAME_SPOT):
    """Draw the source wires again on `level`, between the copies, put where
    the copy is (`where`: mirrored for the other tower...). They go in the
    level's plan where the wires pasted with the fixtures are, or else in
    its plan like the source one (plan.target_view; on the source floor, the
    source plan itself). Wires touching none of the source's elements are
    not the source's (the other tower's, on the same floor). circuited: the
    target keys on a circuit now; a wire is drawn only when the elements it
    connects (panels aside) are on one."""
    dz = level.Elevation - wires.elevation
    source_keys = set(source.elements)
    ours = []
    for wire, info in wires.source:
        ends = _end_links(wire)
        if any(e is not None and e[0] in source_keys for e in ends):
            ours.append((wire, info, ends))
        # else not connected to anything (a drafting wire, or one pasted for
        # the other tower), or of circuits not copied
    existing = wires.on_level(level, set(id_int(w.Id) for w, _, _ in ours))
    same_floor = id_int(level.Id) == wires.source_level
    claimed = set()
    todo = []
    votes = {}                      # source view key -> {target view key: wires there}
    for wire, info, ends in ours:
        if any(e is not None and e[0] not in copies for e in ends):
            result.wires["no_copy"] += 1
            _unwired(result, targets, [copies.get(e[0]) for e in ends if e is not None])
            continue
        wanted = [copies[e[0]] if e is not None else None for e in ends]
        if any(e is not None and e[0] not in source.panels and w not in circuited
               for e, w in zip(ends, wanted)):
            result.wires["no_circuit"] += 1
            continue
        conns = [_connector_of(targets[w], e[1]) if e is not None else None
                 for w, e in zip(wanted, ends)]
        if any(e is not None and c is None for e, c in zip(ends, conns)):
            result.wires["no_copy"] += 1
            _unwired(result, targets, wanted)
            continue
        points = []
        for p in _vertices(wire):
            x, y = where.apply(p.X, p.Y)
            points.append(XYZ(x, y, p.Z + dz))
        same_kind = [k for k in existing if wires.infos_by_key[k].view_type == info.view_type]
        there, key = _find_there(existing, same_kind, points, tolerance, claimed)
        if there is not None:
            claimed.add(id_int(there.Id))
        if key is not None:
            tally = votes.setdefault(info.key, {})
            tally[key] = tally.get(key, 0) + 1
        todo.append((wire, info, wanted, conns, points, there, key))

    chosen = {}
    for wire, info, wanted, conns, points, there, key in todo:
        if info.key not in chosen:
            tally = votes.get(info.key)
            if tally:
                chosen[info.key] = sorted(tally, key=lambda k: (-tally[k], k))[0]
            elif same_floor:
                chosen[info.key] = info.key
            else:
                found = plan.target_view(info, wires.infos, level.Name)
                chosen[info.key] = found.key if found is not None else None
        view_key = key if key is not None else chosen[info.key]
        if view_key is None:
            result.wires["no_view"] += 1
            _unwired(result, targets, wanted)
            continue
        if there is not None and there.IsValidObject:
            if _connected_as(there, wanted):
                result.wires["kept"] += 1
                continue
            if there in existing.get(key, ()):
                existing[key].remove(there)
            wires.doc.Delete(there.Id)
            result.wires["removed"] += 1
        view = wires.views[view_key]
        new, error = None, None
        for attempt in (points, _snapped(points, conns)):
            try:
                new = Wire.Create(wires.doc, wire.GetTypeId(), view.Id, wire.WiringType,
                                  List[XYZ](attempt), conns[0], conns[1])
                break
            except Exception as e:
                error = _message(e)
        if new is None:
            result.wires["refused"] += 1
            if error and error not in result.wire_errors and len(result.wire_errors) < 3:
                result.wire_errors.append(error)
            _unwired(result, targets, wanted)
            continue
        copy_parameters(wire, new)
        wires.add(new, view_key)
        result.wires["drawn"] += 1
        result.wire_views[view.Name] = result.wire_views.get(view.Name, 0) + 1


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


MM_PER_FOOT = 304.8
M_PER_FOOT = 0.3048
Z_TOLERANCE = 0.5 / 0.3048      # ft: a copy is at the same height above its floor, within this


def panel_name(element):
    try:
        name = element.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_NAME).AsString()
        if name:
            return name
    except Exception:
        pass
    try:
        return element.Name or ""
    except Exception:
        return ""


def _panels_by_name(doc):
    found = {}
    collector = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType()
    for e in collector:
        name = panel_name(e).strip().upper()
        if name and name not in found:
            found[name] = e
    return found


def _equipment(doc, type_keys, family_keys):
    """Electrical equipment of these family types (or families), as plan.Items."""
    found = []
    collector = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType()
    for e in collector:
        if _type_key(e) in type_keys or _family_key(e) in family_keys:
            item = _item(e)
            if item is not None:
                found.append((item, e))
    return found


def _at(candidates, mine, x, y, tolerance, z, z_limit):
    """The candidate of mine's family type (else of its family) within
    tolerance of (x, y) in plan and z_limit of z: the nearest in height,
    then in plan. None when there is none."""
    for same_type in (True, False):
        best = None
        for item in candidates:
            if same_type:
                if item.type_key != mine.type_key:
                    continue
            elif mine.family_key is None or item.family_key != mine.family_key:
                continue
            d = ((item.x - x) ** 2 + (item.y - y) ** 2) ** 0.5
            up = abs(item.z - z)
            if d > tolerance or up > z_limit:
                continue
            if best is None or (up, d) < best[0]:
                best = ((up, d), item)
        if best is not None:
            return best[1]
    return None


def _nearest(candidates, mine, x, y):
    """mm from (x, y) to the nearest candidate of mine's family type, or None."""
    found = None
    for item in candidates:
        if item.type_key == mine.type_key:
            d = ((item.x - x) ** 2 + (item.y - y) ** 2) ** 0.5 * MM_PER_FOOT
            found = d if found is None else min(found, d)
    return found


def match_panels(doc, source, target, copies, level, where, tolerance, dz=0.0):
    """[plan.PanelMatch] of the source circuits' panels, and {source panel
    key: target key} of those on other floors (None when the copy is at the
    same spot: they feed the copies too).

    A panel on the source floor is its copy's. For a same-spot copy, one not
    found at its spot is looked for by name (floor number swapped), anywhere
    in the model. For a copy somewhere else (the other tower), it is looked
    for where `where` puts it, among every panel of the floor: the source
    floor's own too, as a panel on the axis between the towers feeds both.
    A panel on another floor is looked for where `where` puts it on its own
    floor: the other tower's riser board, or itself when on the axis; with
    none there, the same panel feeds the copy (the row says to check it).
    Panels found are added to copies or the remote map, and to
    target.elements."""
    same_spot = where.is_same_spot(tolerance) and \
        id_int(level.Id) != id_int(source.level.Id)
    copy_name = None if same_spot else where.describe(tolerance, M_PER_FOOT)
    here, away = {}, {}
    for c in source.circuits:
        if c.panel is None:
            continue
        counts = here if c.panel_here else away
        counts[c.panel] = counts.get(c.panel, 0) + 1
    items = dict((i.key, i) for i in source.items)
    by_name = None
    found = []
    for key in sorted(here, key=lambda k: panel_name(source.elements[k])):
        name = panel_name(source.elements[key])
        if key in copies:
            found.append(plan.PanelMatch(name, plan.BY_SPOT,
                                         panel_name(target.elements[copies[key]]),
                                         circuits=here[key], where=copy_name))
            continue
        mine = items.get(key)
        if not same_spot:
            other = None
            if mine is not None:
                x, y = where.apply(mine.x, mine.y)
                other = _at(target.all_items, mine, x, y, tolerance, mine.z + dz, Z_TOLERANCE)
            if other is not None:
                copies[key] = other.key
                how = plan.ITSELF if other.key == key else plan.BY_SPOT
                found.append(plan.PanelMatch(name, how,
                                             panel_name(target.elements[other.key]),
                                             circuits=here[key], where=copy_name))
                continue
            nearest = None
            if mine is not None:
                nearest = _nearest(target.all_items, mine, *where.apply(mine.x, mine.y))
            found.append(plan.PanelMatch(name, plan.NOT_FOUND, nearest=nearest,
                                         circuits=here[key], where=copy_name))
            continue
        want = plan.floor_name(name, source.level.Name, level.Name)
        if want is not None:
            if by_name is None:
                by_name = _panels_by_name(doc)
            other = by_name.get(want.strip().upper())
            if other is not None and id_int(other.Id) not in copies.values():
                copies[key] = id_int(other.Id)
                target.elements[copies[key]] = other
                found.append(plan.PanelMatch(name, plan.BY_NAME, panel_name(other), want,
                                             circuits=here[key]))
                continue
        nearest = _nearest(target.items, mine, mine.x, mine.y) if mine is not None else None
        found.append(plan.PanelMatch(name, plan.NOT_FOUND, looked_for=want, nearest=nearest,
                                     circuits=here[key]))
    if same_spot or not away:
        return found, None
    remote = {}
    panels = dict((k, source.panels[k]) for k in away)
    mine_items = dict((k, _item(e)) for k, e in panels.items())
    candidates = _equipment(
        doc, set(i.type_key for i in mine_items.values() if i is not None),
        set(i.family_key for i in mine_items.values()
            if i is not None and i.family_key is not None))
    elements = dict((item.key, e) for item, e in candidates)
    names = dict((id_int(l.Id), l.Name) for l in levels(doc))
    for key in sorted(away, key=lambda k: panel_name(panels[k])):
        name = panel_name(panels[key])
        mine = mine_items[key]
        on = names.get(level_key(panels[key]))
        best = None
        if mine is not None:
            x, y = where.apply(mine.x, mine.y)
            best = _at([i for i, _ in candidates], mine, x, y, tolerance, mine.z, STOREY / 2)
        if best is None:
            remote[key] = key
            target.elements[key] = panels[key]
            found.append(plan.PanelMatch(name, plan.FALLBACK, name, circuits=away[key],
                                         where=copy_name, level=on))
            continue
        remote[key] = best.key
        target.elements[best.key] = elements[best.key]
        how = plan.ITSELF if best.key == key else plan.BY_SPOT
        found.append(plan.PanelMatch(name, how, panel_name(elements[best.key]),
                                     circuits=away[key], where=copy_name, level=on))
    return found, remote


def _make(doc, source, target, jobs, result):
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
            panel = target.elements.get(job.panel) or src.BaseEquipment
            try:
                system.SelectPanel(panel)
            except Exception as error:
                panel_error = _message(error)
        copy_parameters(src, system)
        result.made.append(Made(job, system.Id, panel_error))


def copy_to(doc, source, level, tolerance, wires=None):
    """Make the source circuits on `level`, on each copy of the source found
    there (placement.find: the same spot, or the other tower mirrored...).
    On the source floor itself, only copies elsewhere are looked for.
    Returns a LevelResult per copy, or one saying nothing was found."""
    type_keys = set(i.type_key for i in source.items)
    family_keys = set(i.family_key for i in source.items if i.family_key is not None)
    target = read_target(doc, level, type_keys, family_keys, exclude=set(source.elements))
    dz = level.Elevation - source.level.Elevation
    same_floor = id_int(level.Id) == id_int(source.level.Id)
    panels = set(c.panel for c in source.circuits if c.panel_here)
    panel_types = set(i.type_key for i in source.items if i.key in panels)
    panel_families = set(i.family_key for i in source.items
                         if i.key in panels and i.family_key is not None)
    panel_targets = [i for i in target.all_items
                     if i.type_key in panel_types or i.family_key in panel_families]
    found = placing.find(source.items, target.items, tolerance, dz, Z_TOLERANCE, panels,
                         panel_targets, same_floor)
    if not found:
        if same_floor:
            result = LevelResult(level.Name)
            result.note = "No other copy of the circuits of %s found on %s (mirrored, " \
                          "turned or moved, like the other tower)." % (level.Name, level.Name)
            return [result]
        found = [placing.Copy(placing.SAME_SPOT, {}, set())]
    results = []
    matched = set()

    t = Transaction(doc, "Copy circuits to %s" % level.Name)
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(_Quiet())
    t.SetFailureHandlingOptions(options)
    t.Start()
    try:
        for copy in found:
            where = copy.placement
            same_spot = where.is_same_spot(tolerance) and not same_floor
            result = LevelResult(level.Name, None if same_spot else
                                 where.describe(tolerance, M_PER_FOOT))
            copies = dict(copy.copies)
            result.by_family = len(copy.by_family)
            result.found = len([k for k in copies if k not in panels])
            result.total = len([i for i in source.items if i.key not in panels])
            result.panels, remote = match_panels(doc, source, target, copies, level, where,
                                                 tolerance, dz)
            jobs, result.skipped = plan.plan(source.circuits, copies, target.circuited,
                                             remote)
            _make(doc, source, target, jobs, result)
            for made in result.made:        # the next copy leaves them alone
                for k in made.job.elements:
                    target.circuited.add((k, made.job.circuit.kind))
            if wires is not None:
                copy_wires(wires, copies, target.elements, level, tolerance, result, source,
                           set(k for k, _ in target.circuited), where)
            matched |= set(copies.values())
            results.append(result)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    circuited = set(k for k, _ in target.circuited)
    results[-1].left = [target.elements[i.key].Id for i in target.items
                        if i.key not in matched and i.key not in circuited]
    return results
