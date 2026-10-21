# -*- coding: utf-8 -*-
"""Revit side of Mirror Tower (Mechanical / Plumbing).

The tool's elements are read once (read_model), each as a plan.Thing on
its floor and its side (rules: mechanical or plumbing). On each chosen
floor, the Tower 1 elements Tower 2 has not got yet are mirrored in ONE
Revit Mirror (ElementTransformUtils.MirrorElements, copies), so the
copies keep their connections to each other, and moved into Tower 2,
like the electrical Mirror Tower. Elements on a wall are placed again on
Tower 2's wall (mirrortower.revit_mirror._rehost): a move off a wall's
plane is dropped by Revit. Then the open ends of the copies are joined to
any open end at the same spot (Tower 2's own pipes, a re-placed fixture).

No parameter is created: the copies keep Tower 1's values as Revit's
Mirror does, and re-placed ones get them copied over.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ConnectorType, Domain, ElementId,
    ElementTransformUtils, FamilyInstance, FilteredElementCollector, LocationCurve,
    LocationPoint,
)
from System.Collections.Generic import List

from copycircuits import revit_copy as rc
from mepmirror import plan, rules
from mirrortower import revit_mirror

id_int = rc.id_int
_INVALID = id_int(ElementId.InvalidElementId)


def _bic(name):
    return getattr(BuiltInCategory, name, None)


def categories(domain, unticked=()):
    """{category id (int): BuiltInCategory name} the tool takes, but the
    ones unticked in Setup."""
    found = {}
    for name, _ in rules.CATEGORIES[domain]:
        bic = _bic(name)
        if bic is not None and name not in unticked:
            found[int(bic)] = name
    return found


def _category(element):
    try:
        return id_int(element.Category.Id)
    except Exception:
        return None


def _get(doc, key):
    return revit_mirror._get(doc, key)


# ---------------------------------------------------------------- reading

def connectors(element):
    manager = None
    try:
        manager = element.ConnectorManager           # ducts, pipes, flexes
    except Exception:
        pass
    if manager is None:
        try:
            manager = element.MEPModel.ConnectorManager
        except Exception:
            manager = None
    if manager is None:
        return []
    try:
        return list(manager.Connectors)
    except Exception:
        return []


def _text(element, name):
    bip = getattr(BuiltInParameter, name, None)
    if bip is None:
        return u""
    try:
        p = element.get_Parameter(bip)
        if p is None:
            return u""
        return p.AsString() or p.AsValueString() or u""
    except Exception:
        return u""


def _pipe_domain(element):
    names = [_text(element, n) for n in ("RBS_SYSTEM_NAME_PARAM", "RBS_PIPING_SYSTEM_TYPE_PARAM",
                                         "RBS_SYSTEM_ABBREVIATION_PARAM")]
    return rules.pipe_domain(_text(element, "RBS_SYSTEM_CLASSIFICATION_PARAM"), names)


def _equipment_domain(element):
    ducts, pipes = 0, []
    for c in connectors(element):
        try:
            if c.Domain == Domain.DomainHvac:
                ducts += 1
            elif c.Domain == Domain.DomainPiping:
                names = []
                try:
                    if c.MEPSystem is not None:
                        names.append(c.MEPSystem.Name)
                except Exception:
                    pass
                pipes.append(rules.pipe_domain(u"%s" % c.PipeSystemType, names))
        except Exception:
            pass
    return rules.equipment_domain(ducts, pipes)


def _neighbours(element):
    found = []
    for c in connectors(element):
        try:
            for other in c.AllRefs:
                owner = other.Owner
                if owner is not None and id_int(owner.Id) != id_int(element.Id):
                    found.append(id_int(owner.Id))
        except Exception:
            pass
    return found


def _label(element, category):
    try:
        return u"%s : %s" % (element.Symbol.Family.Name, element.Name)
    except Exception:
        pass
    name = rules.LABELS.get(category)
    if name is None:
        try:
            name = element.Category.Name
        except Exception:
            name = u""
    try:
        kind = element.Document.GetElement(element.GetTypeId())
        return u"%s : %s" % (name, kind.Name if kind else u"")
    except Exception:
        return name or u"(unknown)"


def thing(element, category=None):
    """plan.Thing of a duct, pipe or family instance, or None."""
    location = element.Location
    a = b = None
    if isinstance(location, LocationCurve):
        try:
            curve = location.Curve
            p, q = curve.GetEndPoint(0), curve.GetEndPoint(1)
            a, b = (p.X, p.Y, p.Z), (q.X, q.Y, q.Z)
        except Exception:
            return None
    elif isinstance(location, LocationPoint):
        p = location.Point
        a = (p.X, p.Y, p.Z)
    else:
        return None
    try:
        grouped = id_int(element.GroupId) != _INVALID
    except Exception:
        grouped = False
    return plan.Thing(id_int(element.Id), rc._type_key(element), a, b, rc._family_key(element),
                      rc.level_key(element), _label(element, category), grouped)


class Model(object):
    """The tool's elements, read once: by floor, with the floors' heights."""

    def __init__(self):
        self.floors = []            # [(level key, low, high)] all levels
        self.names = {}             # level key -> name
        self.levels = {}            # level key -> Level
        self.things = {}            # level key -> [Thing]
        self.elements = {}          # key -> element
        self.categories = {}        # key -> BuiltInCategory name
        self.other_side = 0         # pipes / equipment that are the other tool's


def read_model(doc, domain, unticked=()):
    cats = categories(domain, unticked)
    model = Model()
    all_levels = rc.levels(doc)
    for level in all_levels:
        f = rc.Floor(level, all_levels)
        model.floors.append((f.key, f.low, f.high))
        model.names[f.key] = level.Name
        model.levels[f.key] = level
    pending, sides, neighbours = {}, {}, {}
    for cat_id, name in cats.items():
        for e in FilteredElementCollector(doc).OfCategory(_bic(name)) \
                .WhereElementIsNotElementType():
            try:
                if isinstance(e, FamilyInstance) and e.SuperComponent is not None:
                    continue            # nested: goes with its parent
            except Exception:
                pass
            t = thing(e, name)
            if t is None:
                continue
            pending[t.key] = (t, e, name)
            if name in rules.PIPED:
                sides[t.key] = _pipe_domain(e)
            elif name in rules.EQUIPMENT:
                sides[t.key] = _equipment_domain(e)
            else:
                sides[t.key] = rules.FIXED.get(name, domain)
    for key, side in sides.items():
        if side is None:
            neighbours[key] = _neighbours(pending[key][1])
    sides = rules.settle(sides, neighbours)
    for key, (t, e, name) in pending.items():
        if sides[key] != domain:
            model.other_side += 1
            continue
        floor = plan.pick_floor(t, model.floors)
        if floor is None:
            continue
        model.things.setdefault(floor, []).append(t)
        model.elements[key] = e
        model.categories[key] = name
    return model


# ---------------------------------------------------------------- mirroring

class FloorResult(object):
    """What happened on one floor."""

    def __init__(self, name):
        self.floor = name
        self.tower1 = 0             # Tower 1 elements
        self.already = 0            # of them, in Tower 2 already
        self.shared = 0             # on the mirror line, not mirrored
        self.leaves = []            # ids of runs leaving Tower 1: skipped
        self.grouped = []           # ids of Tower 1 elements in groups: skipped
        self.mirrored = []          # new element ids
        self.rehosted = 0           # of them, placed again on Tower 2's walls
        self.off_spot = []          # new ids Revit kept off their Tower 2 spot
        self.joined = 0             # open ends joined
        self.no_wall = []           # Tower 1 ids with no wall at their Tower 2 spot
        self.refused = []           # Tower 1 ids Revit did not mirror
        self.errors = []            # what Revit said
        self.why = {}               # (family : type, why not placed) -> count


def _id_list(ids):
    found = List[ElementId]()
    for i in ids:
        found.Add(i)
    return found


def _mirror(doc, elements, plane, result):
    """Mirror copies of the elements, all at once (they stay connected);
    one by one if Revit refuses the lot. Returns the new ElementIds."""
    ids = _id_list([e.Id for e in elements])
    try:
        if ElementTransformUtils.CanMirrorElements(doc, ids):
            made = ElementTransformUtils.MirrorElements(doc, ids, plane, True)
            if made is not None:
                return list(made)
    except Exception as error:
        text = rc._message(error)
        if text not in result.errors:
            result.errors.append(text)
    made = []
    for e in elements:
        try:
            one = _id_list([e.Id])
            if not ElementTransformUtils.CanMirrorElements(doc, one):
                result.refused.append(e.Id)
                continue
            new = ElementTransformUtils.MirrorElements(doc, one, plane, True)
            made.extend(list(new) if new is not None else [])
        except Exception as error:
            result.refused.append(e.Id)
            text = rc._message(error)
            if text not in result.errors:
                result.errors.append(text)
    return made


def _walls(doc, things, placement, floor):
    spots = [placement.apply(t.a[0], t.a[1]) for t in things]
    pad = 5.0
    extent = (min(x for x, _ in spots) - pad, min(y for _, y in spots) - pad,
              max(x for x, _ in spots) + pad, max(y for _, y in spots) + pad)
    _, low, high = floor
    return revit_mirror.WallIndex(doc, extent, low, high if high is not None else low + 30.0)


def _open_ends(doc, keys):
    """[(owner key, connector id, (x, y, z), domain)] of the elements' free
    duct and pipe ends."""
    ends = []
    for key in keys:
        e = _get(doc, key)
        if e is None:
            continue
        for c in connectors(e):
            try:
                if c.ConnectorType != ConnectorType.End or c.IsConnected:
                    continue
                if c.Domain not in (Domain.DomainHvac, Domain.DomainPiping):
                    continue
                o = c.Origin
                ends.append((key, c.Id, (o.X, o.Y, o.Z), u"%s" % c.Domain))
            except Exception:
                pass
    return ends


def _connector(doc, key, connector_id):
    e = _get(doc, key)
    for c in connectors(e) if e is not None else []:
        try:
            if c.Id == connector_id:
                return c
        except Exception:
            pass
    return None


def join_open_ends(doc, new_keys, around_keys):
    """Connect each free end of the new elements to a free end at the same
    spot (of another new one or one of `around_keys`). Returns how many."""
    new_keys = set(new_keys)
    ends = _open_ends(doc, list(new_keys) + [k for k in around_keys if k not in new_keys])
    joined = 0
    for e, f in plan.joints(ends):
        if e[0] not in new_keys and f[0] not in new_keys:
            continue
        a, b = _connector(doc, e[0], e[1]), _connector(doc, f[0], f[1])
        if a is None or b is None:
            continue
        try:
            a.ConnectTo(b)
            joined += 1
        except Exception:
            pass
    return joined


def _on_a_face(element):
    """A hosted family facing sideways: on a wall Revit's move could not
    carry it off (equipment standing free is never re-placed)."""
    try:
        hosted = element.Host is not None or element.HostFace is not None
    except Exception:
        hosted = False
    facing = revit_mirror._facing_out(element)
    return hosted and facing is not None and abs(facing[2]) < 0.3


def mirror_floor(doc, model, floor, side, placement, about, tolerance, join=True):
    """Mirror the floor's missing Tower 1 elements into Tower 2. floor:
    (level key, low, high). Returns a FloorResult."""
    key, _, _ = floor
    result = FloorResult(model.names.get(key, u""))
    result.tower1 = len(side.tower1)
    result.already = len(side.copies)
    result.shared = len(side.shared)
    result.leaves = [model.elements[t.key].Id for t in side.leaves]
    result.grouped = [model.elements[t.key].Id for t in side.grouped]
    if not side.missing:
        return result
    level = model.levels.get(key)
    elements = dict((t.key, model.elements[t.key]) for t in side.missing)
    walled = [t for t in side.missing if not t.run and revit_mirror.on_wall(elements[t.key])]
    walled_keys = set(t.key for t in walled)
    rest = [t for t in side.missing if t.key not in walled_keys]
    del revit_mirror._ERRORS[:]
    tx = revit_mirror._transaction(doc, "Mirror Tower: %s" % result.floor)
    tx.Start()
    try:
        walls, made = None, {}          # Tower 1 key -> new element
        if walled:
            walls = _walls(doc, walled, placement, floor)
            made.update(revit_mirror._rehost(doc, [t.key for t in walled], elements, placement,
                                             walls, level, result))
            result.rehosted = len(made)
        if rest:
            plane, move = revit_mirror._plane(placement, about)
            new_ids = _mirror(doc, [elements[t.key] for t in rest], plane, result)
            # the copies of the tool's categories (not the insulation that comes along)
            cats = set(int(_bic(n)) for n in set(model.categories.values()))
            ours = [e for e in (doc.GetElement(i) for i in new_ids)
                    if e is not None and _category(e) in cats]
            if ours and move.GetLength() > 1e-9:
                ElementTransformUtils.MoveElements(doc, _id_list([e.Id for e in ours]), move)
            doc.Regenerate()
            things = {}
            for e in ours:
                if isinstance(e, FamilyInstance) and e.SuperComponent is not None:
                    continue
                t = thing(e)
                if t is None:
                    result.off_spot.append(e.Id)
                    continue
                things[t.key] = (t, e)
            found = plan.landed(rest, [t for t, _ in things.values()], placement, tolerance)
            back = dict((n, k) for k, n in found.items())
            for n, (t, e) in things.items():
                if n in back:
                    made[back[n]] = e
                elif not t.run and isinstance(e, FamilyInstance) and _on_a_face(e):
                    doc.Delete(e.Id)        # kept on Tower 1's wall plane: placed again
                else:
                    result.off_spot.append(e.Id)
            again = [t for t in rest if t.key not in found and _on_a_face(elements[t.key])
                     and not t.run]
            if again:
                if walls is None:
                    walls = _walls(doc, again, placement, floor)
                placed = revit_mirror._rehost(doc, [t.key for t in again], elements, placement,
                                              walls, level, result)
                made.update(placed)
                result.rehosted += len(placed)
            doc.Regenerate()
        if join and made:
            around = [t.key for t in side.pool] + [t.key for t in side.shared]
            result.joined = join_open_ends(doc, [id_int(e.Id) for e in made.values()], around)
        tx.Commit()
    except Exception:
        if tx.HasStarted() and not tx.HasEnded():
            tx.RollBack()
        raise
    for text in revit_mirror._ERRORS:
        if text not in result.errors:
            result.errors.append(text)
    refused = set(id_int(i) for i in result.refused) | set(id_int(i) for i in result.no_wall)
    for k, e in made.items():
        if e is None or not e.IsValidObject:
            if k not in refused:
                result.refused.append(elements[k].Id)
            continue
        result.mirrored.append(e.Id)
    result.off_spot = [i for i in result.off_spot if doc.GetElement(i) is not None]
    return result
