# -*- coding: utf-8 -*-
"""Revit side of Mirror Tower.

Two passes over the chosen floors, in one undo:

1. Elements. The electrical elements of Tower 1 (in its scope box) are
   paired with Tower 2's (same family type at the mirrored spot, or a
   board named like it with B1 -> B2). Those Tower 2 has not got yet are
   mirrored with Revit's own Mirror (ElementTransformUtils.MirrorElements:
   same types, same parameter values, flipped) and moved into Tower 2;
   the mirrored boards are renamed (B1 -> B2).
2. Circuits and wires. Each circuit of Tower 1 is made again on the
   copies, on Tower 2's board (copycircuits.plan / _make), with the
   source circuit's parameters, and its wires are drawn again mirrored
   in the same plan (copycircuits copy_wires).

No parameter is created: only existing ones are read and set.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math
import time

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, CurveElement, ElementId, ElementTransformUtils,
    FailureProcessingResult, FailureSeverity, FamilyInstance, FamilyPlacementType,
    FilteredElementCollector, GeometryInstance, Grid, IFailuresPreprocessor, Line, Options,
    PlanarFace, Plane, Solid, Transaction, Transform, Wall, XYZ,
)
from Autodesk.Revit.DB.Structure import StructuralType
from System.Collections.Generic import List

from copycircuits import placement as placing
from copycircuits import plan
from copycircuits import revit_copy as rc
from copycircuits.report import LevelResult
from mirrortower import geometry, pairing

try:
    from firealarm.revit_fa import linked_models
except Exception:                       # pragma: no cover
    def linked_models(doc):
        return []

id_int = rc.id_int
_INVALID_ID = id_int(ElementId.InvalidElementId)

CATEGORIES = ("OST_LightingFixtures", "OST_LightingDevices", "OST_ElectricalFixtures",
              "OST_ElectricalEquipment", "OST_FireAlarmDevices", "OST_DataDevices",
              "OST_CommunicationDevices", "OST_SecurityDevices", "OST_TelephoneDevices",
              "OST_NurseCallDevices")
_CATEGORY_IDS = set()
for _name in CATEGORIES:
    _bic = getattr(BuiltInCategory, _name, None)
    if _bic is not None:
        _CATEGORY_IDS.add(int(_bic))
_EQUIPMENT = int(BuiltInCategory.OST_ElectricalEquipment)


def _get(doc, key):
    """The element with id `key` (an int), or None."""
    try:
        from System import Int64
        return doc.GetElement(ElementId(Int64(key)))     # Revit 2024+
    except Exception:
        pass
    try:
        return doc.GetElement(ElementId(int(key)))
    except Exception:
        return None


def _category(element):
    try:
        return id_int(element.Category.Id)
    except Exception:
        return None


def is_board(element):
    return _category(element) == _EQUIPMENT


# ---------------------------------------------------------------- picking

def scope_boxes(doc):
    """[(name, scope box)] by name."""
    found = []
    for e in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_VolumeOfInterest).WhereElementIsNotElementType():
        found.append((e.Name or u"(no name)", e))
    found.sort(key=lambda p: p[0].lower())
    return found


def outline(box):
    """The scope box's outline in plan: convex hull of its edges' ends."""
    points = []
    geom = box.get_Geometry(Options())
    if geom is not None:
        for obj in geom:
            try:
                for p in (obj.GetEndPoint(0), obj.GetEndPoint(1)):
                    points.append((p.X, p.Y))
            except Exception:
                pass
    if len(points) < 3:
        b = box.get_BoundingBox(None)
        if b is not None:
            points = [(b.Min.X, b.Min.Y), (b.Max.X, b.Min.Y), (b.Max.X, b.Max.Y),
                      (b.Min.X, b.Max.Y)]
    return geometry.hull(points)


def line_ends(element, transform=None):
    """((x, y), (x, y)) of a grid or straight model/detail line, or None."""
    curve = None
    if isinstance(element, Grid):
        curve = element.Curve
    elif isinstance(element, CurveElement):
        curve = element.GeometryCurve
    if curve is None or not isinstance(curve, Line):
        return None
    a, b = curve.GetEndPoint(0), curve.GetEndPoint(1)
    if transform is not None:
        a, b = transform.OfPoint(a), transform.OfPoint(b)
    return (a.X, a.Y), (b.X, b.Y)


# ---------------------------------------------------------------- reading

def _electrical_on(doc, floor):
    """{key: (plan.Item, element)} of the electrical family instances on the floor."""
    found = {}
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
        if _category(e) not in _CATEGORY_IDS:
            continue
        try:
            if e.SuperComponent is not None:
                continue            # nested: goes with its parent
        except Exception:
            pass
        if not floor.has(e)[0]:
            continue
        item = rc._item(e)
        if item is not None:
            found[item.key] = (item, e)
    return found


class Side(object):
    """One floor split by tower."""

    def __init__(self, level, floor):
        self.level = level
        self.floor = floor
        self.tower1 = {}            # key -> (Item, element): Tower 1's, to mirror
        self.on_line = {}           # key -> (Item, element): on the mirror line, shared
        self.pool = {}              # key -> (Item, element): the rest (Tower 2's...)
        self.copies = {}            # Tower 1 key -> Tower 2 key (on-line ones: themselves)
        self.named = set()          # Tower 1 boards whose copy was found by name


def split(doc, level, all_levels, box, placement, tolerance):
    floor = rc.Floor(level, all_levels)
    side = Side(level, floor)
    everything = _electrical_on(doc, floor)
    boxed = [item for item, _ in everything.values()
             if geometry.inside(box, item.x, item.y, tolerance)]
    shared = geometry.own_images(boxed, placement, tolerance)
    boxed = set(i.key for i in boxed)
    for key, pair in everything.items():
        if key in shared:
            side.on_line[key] = pair
        elif key in boxed:
            side.tower1[key] = pair
        else:
            side.pool[key] = pair
    return side


def boards_by_name(doc):
    return rc._panels_by_name(doc)


def _name_twins(side, swap, by_name):
    found = {}
    if not swap or not swap[0]:
        return found
    for key, (item, e) in side.tower1.items():
        if not is_board(e):
            continue
        want = geometry.swap_name(rc.panel_name(e), swap[0], swap[1])
        other = by_name.get(want.strip().upper()) if want else None
        if other is not None and id_int(other.Id) != key:
            found[key] = id_int(other.Id)
    return found


# ---------------------------------------------------------------- failures

_ERRORS = []


class _Resolve(IFailuresPreprocessor):
    """Warnings dismissed; an error Revit can resolve (an element it cannot
    keep) is resolved its default way, so the rest still goes through."""
    __namespace__ = "ElectricalMirrorTower"       # needed by the CPython engine

    def PreprocessFailures(self, accessor):
        resolved = False
        for message in list(accessor.GetFailureMessages()):
            if message.GetSeverity() == FailureSeverity.Warning:
                accessor.DeleteWarning(message)
            elif message.HasResolutions():
                try:
                    text = message.GetDescriptionText()
                except Exception:
                    text = u"refused by Revit"
                if text not in _ERRORS:
                    _ERRORS.append(text)
                accessor.ResolveFailure(message)
                resolved = True
        if resolved:
            return FailureProcessingResult.ProceedWithCommit
        return FailureProcessingResult.Continue


def _transaction(doc, name):
    t = Transaction(doc, name)
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(_Resolve())
    t.SetFailureHandlingOptions(options)
    return t


# ---------------------------------------------------------------- walls

WALL_CATEGORIES = ("OST_Walls", "OST_Columns", "OST_StructuralColumns")
CELL = 10.0                 # ft, plan grid of the wall face index


def _facing_out(element):
    """(x, y, z) the element faces out of its host: its work plane normal for
    a face-based family, else its facing. None when not known."""
    try:
        kind = element.Symbol.Family.FamilyPlacementType
        v = element.GetTotalTransform().BasisZ if kind == FamilyPlacementType.WorkPlaneBased \
            else element.FacingOrientation
        return v.X, v.Y, v.Z
    except Exception:
        return None


def on_wall(element):
    """The element sits on a wall: a face-based family on a vertical face
    (wall here or in a link), or a wall-hosted family. Revit's Mirror +
    Move cannot carry these to Tower 2 (a move off the wall's plane is
    dropped), so they are placed again on Tower 2's wall (_rehost)."""
    try:
        kind = element.Symbol.Family.FamilyPlacementType
    except Exception:
        return False
    host = getattr(element, "Host", None)
    if isinstance(host, Wall):
        return True
    if kind == FamilyPlacementType.WorkPlaneBased:
        try:
            return abs(element.GetTotalTransform().BasisZ.Z) < 0.3
        except Exception:
            return False
    return False


class _WallFace(object):
    def __init__(self, face, transform, link, element, reference):
        self.face = face
        self.inverse = transform.Inverse
        self.link = link
        self.element = element
        self.ref = reference
        n = transform.OfVector(face.FaceNormal)
        o = transform.OfPoint(face.Origin)
        self.normal = (n.X, n.Y, n.Z)
        self.origin = (o.X, o.Y, o.Z)
        xs, ys = [], []
        for loop in face.EdgeLoops:
            for edge in loop:
                for p in edge.Tessellate():
                    p = transform.OfPoint(p)
                    xs.append(p.X)
                    ys.append(p.Y)
        self.box = (min(xs), min(ys), max(xs), max(ys)) if xs else None

    def contains(self, point):
        result = self.face.Project(self.inverse.OfPoint(point))
        return result is not None and result.Distance < 0.01


class WallIndex(object):
    """Vertical faces of walls and columns (this model and, with `links`,
    its links) in an area of a floor, on a plan grid. Read once per floor."""

    def __init__(self, doc, extent, z_low, z_high, links=True):
        self.cells = {}
        self.faces = 0
        options = Options()
        options.ComputeReferences = True
        x0, y0, x1, y1 = extent
        sources = [(None, doc, Transform.Identity)]
        if links:
            sources += [(link, link_doc, link.GetTotalTransform())
                        for link, link_doc in linked_models(doc)]
        for link, source_doc, transform in sources:
            for name in WALL_CATEGORIES:
                bic = getattr(BuiltInCategory, name, None)
                if bic is None:
                    continue
                for element in FilteredElementCollector(source_doc).OfCategory(bic) \
                        .WhereElementIsNotElementType():
                    try:
                        box = element.get_BoundingBox(None)
                        if box is None:
                            continue
                        lo, hi = transform.OfPoint(box.Min), transform.OfPoint(box.Max)
                        if max(lo.Z, hi.Z) < z_low or min(lo.Z, hi.Z) > z_high:
                            continue
                        if max(lo.X, hi.X) < x0 or min(lo.X, hi.X) > x1 or \
                                max(lo.Y, hi.Y) < y0 or min(lo.Y, hi.Y) > y1:
                            continue
                        for face in _vertical_faces(element, options):
                            ref = face.Reference
                            if ref is None:
                                continue
                            if link is not None:
                                ref = ref.CreateLinkReference(link)
                            item = _WallFace(face, transform, link, element, ref)
                            if item.box is not None:
                                self._add(item)
                    except Exception:
                        pass

    def _add(self, item):
        b = item.box
        for i in range(int(math.floor(b[0] / CELL)), int(math.floor(b[2] / CELL)) + 1):
            for j in range(int(math.floor(b[1] / CELL)), int(math.floor(b[3] / CELL)) + 1):
                self.cells.setdefault((i, j), []).append(item)
        self.faces += 1

    def find(self, point, facing):
        """(_WallFace, the point on it) for a copy at `point` (XYZ) facing
        `facing` (x, y, z), or (None, None)."""
        cell = (int(math.floor(point.X / CELL)), int(math.floor(point.Y / CELL)))
        candidates = []
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                candidates.extend(self.cells.get((cell[0] + i, cell[1] + j), ()))
        found = geometry.wall_faces(set(candidates), (point.X, point.Y, point.Z), facing)
        spots = []
        for d, face in found:
            n = face.normal
            on = XYZ(point.X - d * n[0], point.Y - d * n[1], point.Z - d * n[2])
            if face.contains(on):
                return face, on
            spots.append((face, on))
        for face, on in spots:       # just off the face (at its edge, an opening...)
            b = face.box
            if b[0] - 0.5 <= on.X <= b[2] + 0.5 and b[1] - 0.5 <= on.Y <= b[3] + 0.5:
                return face, on
        return None, None


def _vertical_faces(element, options):
    geometry_ = element.get_Geometry(options)
    if geometry_ is None:
        return
    items = []
    for obj in geometry_:
        if isinstance(obj, GeometryInstance):
            items.extend(obj.GetInstanceGeometry())
        else:
            items.append(obj)
    for obj in items:
        if isinstance(obj, Solid) and obj.Faces.Size:
            for face in obj.Faces:
                if isinstance(face, PlanarFace) and abs(face.FaceNormal.Z) < 0.1:
                    yield face


def _walls_for(doc, keys, side, placement):
    """The wall faces around the Tower 2 spots of these Tower 1 elements."""
    spots = [placement.apply(side.tower1[k][0].x, side.tower1[k][0].y) for k in keys]
    pad = 5.0
    extent = (min(x for x, _ in spots) - pad, min(y for _, y in spots) - pad,
              max(x for x, _ in spots) + pad, max(y for _, y in spots) + pad)
    floor = side.floor
    return WallIndex(doc, extent, floor.low,
                     floor.high if floor.high is not None else floor.low + 30.0)


def _label(element):
    try:
        return u"%s : %s" % (element.Symbol.Family.Name, element.Name)
    except Exception:
        return u"(unknown type)"


def _why(result, element, reason):
    key = (_label(element), reason)
    result.why[key] = result.why.get(key, 0) + 1


def _rehost(doc, keys, elements, placement, walls, level, result):
    """Place the wall elements again on Tower 2's walls, at their mirrored
    spot. Returns {Tower 1 key: new element}."""
    made = {}
    for k in keys:
        e = elements[k]
        try:
            t = e.GetTotalTransform()
            p = e.Location.Point
            normal = _facing_out(e)
            if normal is None:
                result.no_wall.append(e.Id)
                continue
            fx, fy = placement.turn(normal[0], normal[1])
            hx, hy = placement.turn(t.BasisX.X, t.BasisX.Y)
            x, y = placement.apply(p.X, p.Y)
            face, on = walls.find(XYZ(x, y, p.Z), (fx, fy, normal[2]))
            if face is None:
                result.no_wall.append(e.Id)
                _why(result, e, u"no wall face at its Tower 2 spot")
                continue
            symbol = e.Symbol
            if not symbol.IsActive:
                symbol.Activate()
            if e.Symbol.Family.FamilyPlacementType == FamilyPlacementType.WorkPlaneBased:
                new = doc.Create.NewFamilyInstance(face.ref, on, XYZ(hx, hy, t.BasisX.Z), symbol)
            elif face.link is None and isinstance(face.element, Wall):
                new = doc.Create.NewFamilyInstance(on, symbol, face.element, level,
                                                   StructuralType.NonStructural)
            else:
                result.no_wall.append(e.Id)
                _why(result, e, u"wall-hosted family, and Tower 2's wall is in a link")
                continue
            rc.copy_parameters(e, new)
            made[k] = new
        except Exception as error:
            result.refused.append(e.Id)
            text = rc._message(error)
            if text not in result.errors:
                result.errors.append(text)
    return made


# ---------------------------------------------------------------- pass 1

class MirrorResult(object):
    """Pass 1 on one floor."""

    def __init__(self, level):
        self.floor = level
        self.tower1 = 0             # Tower 1 elements
        self.already = 0            # of them, with a copy in Tower 2 already
        self.on_line = 0            # on the mirror line (not mirrored)
        self.mirrored = []          # new element ids
        self.refused = []           # Tower 1 element ids Revit did not mirror
        self.errors = []            # what Revit said
        self.renamed = []           # (Tower 1 board name, Tower 2 board name)
        self.not_renamed = []       # Tower 2 board names without the swap text
        self.by_name = []           # (Tower 1 board, Tower 2 board found by name)
        self.rehosted = 0           # of the mirrored, placed again on Tower 2's walls
        self.no_wall = []           # Tower 1 element ids with no wall at their Tower 2 spot
        self.wall_faces = 0         # wall faces read around Tower 2
        self.why = {}               # (family : type, why not placed) -> count
        self.moved_off = 0          # mirrored but not where they should be: removed


def _plane(placement, about):
    """The mirror plane doing `placement` (through `about`) and the move after it."""
    angle, (ax, ay), (dx, dy) = geometry.revit_steps(placement, about)
    normal = XYZ(-math.sin(angle), math.cos(angle), 0)
    return Plane.CreateByNormalAndOrigin(normal, XYZ(ax, ay, 0)), XYZ(dx, dy, 0)


def _ids(keys, elements):
    found = List[ElementId]()
    for k in keys:
        found.Add(elements[k].Id)
    return found


def _mirror(doc, keys, elements, placement, about, result):
    """Mirror copies of the elements, moved where `placement` puts them.
    Returns the new ElementIds."""
    plane, move = _plane(placement, about)
    wanted = list(keys)
    keys = [k for k in wanted if ElementTransformUtils.CanMirrorElements(
        doc, _ids([k], elements))]
    cant = [k for k in wanted if k not in keys]
    made = []
    try:
        new = ElementTransformUtils.MirrorElements(doc, _ids(keys, elements), plane, True)
        made = list(new) if new is not None else []
        if new is None:
            raise TypeError("no ids back")      # older Revit: one by one, to know them
    except Exception:
        made = []
        before = set(id_int(e.Id) for e in FilteredElementCollector(doc).OfClass(FamilyInstance))
        for k in keys:
            try:
                new = ElementTransformUtils.MirrorElements(doc, _ids([k], elements), plane, True)
                if new is not None:
                    made.extend(new)
            except Exception as error:
                cant.append(k)
                text = rc._message(error)
                if text not in result.errors:
                    result.errors.append(text)
        if not made:
            made = [e.Id for e in FilteredElementCollector(doc).OfClass(FamilyInstance)
                    if id_int(e.Id) not in before]
    for k in cant:
        result.refused.append(elements[k].Id)
    if made and move.GetLength() > 1e-9:
        ids = List[ElementId]()
        for i in made:
            ids.Add(i)
        ElementTransformUtils.MoveElements(doc, ids, move)
    return made


def _own_name(board):
    try:
        return board.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_NAME).AsString() or u""
    except Exception:
        return u""


def _rename(source, board, swap, result, by_name, new):
    """Give Tower 2's `board` the name of Tower 1's `source` with the swap
    (B1 -> B2). A board found in Tower 2 (new False) keeps a name of its own
    that is not Tower 1's; a mirrored one with no swap in its name gets
    Tower 1's name + " (2)" so it is not left unnamed."""
    old = rc.panel_name(source)
    p = board.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_NAME)
    if p is None or p.IsReadOnly:
        result.not_renamed.append(old)
        return
    has = _own_name(board)
    if not new and has and has.strip().upper() != old.strip().upper():
        return                      # Tower 2's own name
    want = geometry.swap_name(old, swap[0], swap[1]) if swap and swap[0] else None
    if want is None:
        if new or not has:
            want = old + u" (2)"
            result.not_renamed.append(want)
        else:
            return
    if want == has:
        return
    other = by_name.get(want.strip().upper())
    if other is not None and id_int(other.Id) != id_int(board.Id):
        result.not_renamed.append(u"%s (%s is taken)" % (old, want))
        return
    p.Set(want)
    by_name[want.strip().upper()] = board
    result.renamed.append((old, want))


def mirror_floor(doc, side, placement, about, tolerance, swap, by_name):
    """Pass 1 on one floor: the copies found or made (side.copies). about:
    Tower 1's centre in plan."""
    result = MirrorResult(side.level.Name)
    result.tower1 = len(side.tower1)
    result.on_line = len(side.on_line)
    named = _name_twins(side, swap, by_name)
    side.named = set(named)
    items = [i for i, _ in side.tower1.values()]
    copies, missing = pairing.pair_up(items, [i for i, _ in side.pool.values()], placement,
                                      tolerance, rc.Z_TOLERANCE, named)
    for key in side.on_line:
        copies[key] = key
    for k, t in named.items():
        result.by_name.append((rc.panel_name(side.tower1[k][1]), rc.panel_name(
            side.pool[t][1] if t in side.pool else _get(doc, t))))
    result.already = len([k for k in side.tower1 if k in copies])
    elements = dict((k, e) for k, (_, e) in side.tower1.items())
    unnamed = [(k, t) for k, t in copies.items() if k in side.tower1 and k not in named and
               k != t and is_board(elements[k]) and t in side.pool]
    if unnamed and swap and swap[0]:
        t = _transaction(doc, "Mirror Tower: board names, %s" % side.level.Name)
        t.Start()
        try:
            for k, n in unnamed:
                _rename(elements[k], side.pool[n][1], swap, result, by_name, new=False)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
    if missing:
        del _ERRORS[:]
        t = _transaction(doc, "Mirror Tower: %s" % side.level.Name)
        t.Start()
        try:
            walled = [k for k in missing if on_wall(elements[k])]
            rehosted, walls = {}, None
            if walled:
                walls = _walls_for(doc, walled, side, placement)
                result.wall_faces = walls.faces
                rehosted = _rehost(doc, walled, elements, placement, walls, side.level,
                                   result)
            rest = [k for k in missing if k not in set(walled)]
            new_ids = _mirror(doc, rest, elements, placement, about, result) if rest else []
            doc.Regenerate()
            new = {}
            for i in new_ids:
                e = doc.GetElement(i)
                if isinstance(e, FamilyInstance) and getattr(e, "SuperComponent", None) is None:
                    item = rc._item(e)
                    if item is not None:
                        new[item.key] = (item, e)
            lost = [side.tower1[k][0] for k in rest]
            made = plan.match(placing.moved(lost, placement), [i for i, _ in new.values()],
                              tolerance, 0.0, rc.Z_TOLERANCE)
            # copies that did not land where they should (Revit kept them on their
            # host's plane): removed, and placed again on Tower 2's wall
            stray = [n for n in new if n not in set(made.values())]
            if stray:
                result.moved_off = len(stray)
                for n in stray:
                    doc.Delete(new.pop(n)[1].Id)
                again = [k for k in rest if k not in made and _facing_out(elements[k])
                         is not None and abs(_facing_out(elements[k])[2]) < 0.3]
                if again:
                    if walls is None:
                        walls = _walls_for(doc, again, side, placement)
                        result.wall_faces = walls.faces
                    rehosted.update(_rehost(doc, again, elements, placement, walls,
                                            side.level, result))
                    doc.Regenerate()
            for k, e in rehosted.items():
                item = rc._item(e)
                if item is not None:
                    new[item.key] = (item, e)
                    made[k] = item.key
            for k, n in made.items():
                e = new[n][1]
                if is_board(e):
                    _rename(elements[k], e, swap, result, by_name, new=True)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
        for e in _ERRORS:
            if e not in result.errors:
                result.errors.append(e)
        refused = set(id_int(i) for i in result.refused)
        for k, n in made.items():
            e = _get(doc, n)
            if e is None or not e.IsValidObject:
                if k not in refused:            # Revit took it back on commit
                    result.refused.append(elements[k].Id)
                continue
            copies[k] = n
            side.pool[n] = (new[n][0], e)
            result.mirrored.append(e.Id)
            if k in rehosted:
                result.rehosted += 1
        no_wall = set(id_int(i) for i in result.no_wall)
        for k in missing:
            if k not in made and k not in refused and k not in no_wall:
                result.refused.append(elements[k].Id)
    side.copies = copies
    return result


# ---------------------------------------------------------------- pass 2

class _Target(object):
    def __init__(self):
        self.elements = {}


def _board_at(doc, board, placement, tolerance):
    """Key of the board of the same type (else family) at `board`'s mirrored
    spot, about at its height, anywhere in the model; or None."""
    mine = rc._item(board)
    if mine is None:
        return None
    candidates = [i for i, _ in rc._equipment(
        doc, set([mine.type_key]), set([mine.family_key]) if mine.family_key else set())]
    x, y = placement.apply(mine.x, mine.y)
    found = rc._at(candidates, mine, x, y, tolerance, mine.z, rc.STOREY / 2)
    return found.key if found is not None else None


_DIST = getattr(BuiltInParameter, "RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM", None)


def _system_name(board):
    """Name of the board's distribution system, or u"none"."""
    try:
        sid = board.get_Parameter(_DIST).AsElementId()
        e = board.Document.GetElement(sid)
        return e.Name if e is not None else u"none"
    except Exception:
        return u"none"


def _match_board(source, board):
    """Give Tower 2's board Tower 1's electrical settings: its distribution
    system first (a circuit goes on a board only when they match: "The panel
    and circuit do not match"), then its other writable values but the name.
    Returns (board name, system set) when the system changed, else None."""
    changed = None
    try:
        src = source.get_Parameter(_DIST)
        dst = board.get_Parameter(_DIST)
        if src is not None and dst is not None and not dst.IsReadOnly and \
                id_int(src.AsElementId()) != _INVALID_ID and \
                id_int(src.AsElementId()) != id_int(dst.AsElementId()):
            dst.Set(src.AsElementId())
            changed = (rc.panel_name(board), _system_name(source))
    except Exception:
        pass
    keep = _own_name(board)
    rc.copy_parameters(source, board)
    p = board.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_NAME)
    if p is not None and not p.IsReadOnly and keep and p.AsString() != keep:
        p.Set(keep)
    return changed


def _onto_boards(doc, circuits, copies, target, source, result):
    """Tower 2 circuits left on no board (an earlier run, when the board
    copy had no name): put on the board of the Tower 1 circuit they copy,
    with its parameters. Their keys go in result.onto_boards, failures
    in result.onto_failed."""
    result.onto_boards, result.onto_failed = [], []
    by_element = {}
    for c in circuits:
        for k in c.elements:
            if k in copies:
                by_element.setdefault((copies[k], c.kind), c)
    seen = set()
    for key, e in list(target.elements.items()):
        for system in rc._member_of(e):
            sid = id_int(system.Id)
            if sid in seen:
                continue
            seen.add(sid)
            try:
                if system.BaseEquipment is not None:
                    continue
            except Exception:
                continue
            c = by_element.get((key, rc._kind(system)))
            if c is None or c.panel is None or copies.get(c.panel) is None:
                continue
            board = target.elements.get(copies[c.panel])
            if board is None:
                continue
            try:
                system.SelectPanel(board)
                rc.copy_parameters(source.systems[c.key], system)
                result.onto_boards.append(system.Id)
            except Exception as error:
                result.onto_failed.append((c.label, u"%s (circuit board %s: %s; Tower 2 "
                                           u"board %s: %s)" % (
                                               rc._message(error),
                                               c.panel_name, _system_name(source.panels[c.panel]),
                                               rc.panel_name(board), _system_name(board))))


def circuit_floor(doc, side, placement, tolerance, swap, by_name, wires_on):
    """Pass 2 on one floor: Tower 1's circuits made on Tower 2's copies,
    and their wires drawn. Returns (copycircuits LevelResult, the source
    read: Tower 1's circuits)."""
    result = LevelResult(side.level.Name, u"mirrored")
    tower1 = set(side.tower1)
    only = tower1 | set(side.on_line)
    source = rc.read_source(doc, side.level, only)
    circuits = []
    for c in source.circuits:
        c.elements = [k for k in c.elements if k in only]
        if any(k in tower1 for k in c.elements):
            circuits.append(c)
    source.circuits = circuits
    copies = dict(side.copies)
    target = _Target()
    for key, t in copies.items():
        found = side.pool.get(t) or side.on_line.get(t) or side.tower1.get(t)
        e = found[1] if found is not None else _get(doc, t)
        if e is not None:
            target.elements[t] = e

    boards, counts = {}, {}
    for c in circuits:
        if c.panel is not None:
            boards[c.panel] = source.panels.get(c.panel)
            counts[c.panel] = counts.get(c.panel, 0) + 1
    names = dict((id_int(l.Id), l.Name) for l in rc.levels(doc))
    pairs = []                      # (Tower 1 board, its Tower 2 board)
    for key in sorted(boards, key=lambda k: rc.panel_name(boards[k])):
        board = boards[key]
        name = rc.panel_name(board)
        named = None
        want = geometry.swap_name(name, swap[0], swap[1]) if swap and swap[0] else None
        if key not in copies and want:
            other = by_name.get(want.strip().upper())
            named = id_int(other.Id) if other is not None else None
        spot = None
        if key not in copies and named is None:
            spot = _board_at(doc, board, placement, tolerance)
        t, how = pairing.board_for(key, copies, named, spot, side.named)
        copies[key] = t
        if t not in target.elements:
            target.elements[t] = _get(doc, t)
        if t != key and target.elements[t] is not None:
            pairs.append((board, target.elements[t]))
        on = None if key in side.tower1 or key in side.on_line else names.get(rc.level_key(board))
        result.panels.append(plan.PanelMatch(name, how, rc.panel_name(target.elements[t]),
                                             want, circuits=counts[key], where=u"mirrored",
                                             level=on))
    for c in circuits:
        c.panel_here = True          # every board is in `copies` now
    source.elements = dict((k, e) for k, e in source.elements.items()
                           if k in only or k in boards)
    for k, b in boards.items():
        source.elements[k] = b

    circuited = set()
    for t, e in target.elements.items():
        for system in rc._member_of(e):
            circuited.add((t, rc._kind(system)))
    result.found = len([k for k in tower1 if k in copies and not is_board(side.tower1[k][1])])
    result.total = len([k for k in tower1 if not is_board(side.tower1[k][1])])

    t = _transaction(doc, "Mirror Tower circuits: %s" % side.level.Name)
    t.Start()
    try:
        result.boards_set = [_match_board(a, b) for a, b in pairs]
        result.boards_set = [x for x in result.boards_set if x]
        doc.Regenerate()
        _onto_boards(doc, circuits, copies, target, source, result)
        jobs, result.skipped = plan.plan(circuits, copies, circuited)
        clock = time.time()
        rc._make(doc, source, target, jobs, result)
        result.seconds = {"circuits": time.time() - clock}
        for made in result.made:
            if made.panel_error and made.job.panel is not None:
                c = made.job.circuit
                made.panel_error = u"%s (Tower 1 board %s: %s; Tower 2 board %s: %s)" % (
                    made.panel_error, c.panel_name,
                    _system_name(source.panels.get(c.panel)),
                    rc.panel_name(target.elements.get(made.job.panel)),
                    _system_name(target.elements.get(made.job.panel)))
        if wires_on:
            for made in result.made:
                for k in made.job.elements:
                    circuited.add((k, made.job.circuit.kind))
            wires = rc.Wires(doc, side.level)
            skip = set(k for k in side.pool if k not in set(copies.values()))
            clock = time.time()
            rc.copy_wires(wires, copies, target.elements, side.level, tolerance, result,
                          source, set(k for k, _ in circuited), placement, skip)
            result.seconds["wires"] = time.time() - clock
        clock = time.time()
        t.Commit()
        result.seconds["saving circuits"] = time.time() - clock
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return result, source
