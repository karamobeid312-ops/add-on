# -*- coding: utf-8 -*-
"""Revit side: read the block inserts of a linked or imported DWG and
place lighting fixtures on them.

The ceiling above each block is found like the fire alarm detectors do it
(firealarm.revit_fa.CeilingFinder): a ray shot up from the plan's level
through this model and linked models; the ceiling wins, and the slab is
used only where there is no ceiling below it. A ray per light is slow, so
each ceiling face a ray hits is remembered, and the next lights under the
same face take it without a ray. The fixture family can be
  face-based       placed on the ceiling face (ceiling here or in a link)
  ceiling-hosted   hosted by the ceiling (ceiling in this model only)
  level-based      not hosted (Revit cannot attach it to anything): set at
                   the ceiling's height, or the height set in the window
                   where there is no ceiling or slab above
Where there is no ceiling the face-based lights go on the slab above.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math
import time

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, FamilyInstance, FamilySymbol, FilteredElementCollector,
    ElementId, GeometryInstance, ImportInstance, Options, PlanarFace, Transaction,
    TransactionGroup, Transform, XYZ,
)

from cadlights.match import MM_PER_FOOT, Block, Result, clean_name, normal_angle, split_spots
from firealarm.revit_fa import (HOSTED, LEVEL, CeilingFinder, Hit, _place, _ray_view,
                                placement_kind, type_label)

LIGHT_CATEGORY = BuiltInCategory.OST_LightingFixtures
ABOVE_LEVEL = 25.0          # ft above the level where existing lights still count
RAY_START = 1.0             # ft above the level where a ceiling can start
CELL = 10.0                 # ft, grid cell of the face index


def _id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


# ---------------------------------------------------------------- CAD

def is_cad(element):
    return isinstance(element, ImportInstance)


def cad_label(cad):
    try:
        name = cad.Category.Name if cad.Category is not None else ""
    except Exception:
        name = ""
    return name or "CAD"


def _element_name(element):
    """Name of any element; Element.Name is hidden on some element classes
    (and under CPython), so try the property, its getter and the type name
    parameters."""
    if element is None:
        return ""
    try:
        name = element.Name
        if name:
            return name
    except Exception:
        pass
    from Autodesk.Revit.DB import BuiltInParameter, Element
    for getter in (lambda: Element.Name.GetValue(element),        # IronPython
                   lambda: Element.Name.__get__(element)):         # CPython
        try:
            name = getter()
            if name:
                return name
        except Exception:
            pass
    for bip in (BuiltInParameter.SYMBOL_NAME_PARAM, BuiltInParameter.ALL_MODEL_TYPE_NAME):
        try:
            p = element.get_Parameter(bip)
            if p is not None and p.AsString():
                return p.AsString()
        except Exception:
            pass
    return ""


def _block_name(doc, geometry):
    """Raw name of the block a GeometryInstance is an insert of."""
    try:
        symbol_id = geometry.GetSymbolGeometryId().SymbolId     # Revit 2023+
    except Exception:
        symbol_id = None
    if symbol_id is not None:
        docs = []
        try:
            docs.append(geometry.GetDocument())                  # the symbol's document
        except Exception:
            pass
        docs.append(doc)
        for source in docs:
            try:
                name = _element_name(source.GetElement(symbol_id))
            except Exception:
                name = ""
            if name:
                return name
    try:
        return _element_name(geometry.Symbol)                    # older Revit
    except Exception:
        return ""


def _layer(doc, geometry):
    try:
        style = doc.GetElement(geometry.GraphicsStyleId)
        return style.GraphicsStyleCategory.Name if style is not None else ""
    except Exception:
        return ""


def _inserts(doc, cad, view):
    options = Options()
    if view is not None:
        options.View = view
    found = []
    geometry = cad.get_Geometry(options)
    if geometry is None:
        return found
    for top in geometry:
        if not isinstance(top, GeometryInstance):
            continue
        outer = top.Transform               # CAD -> this model
        for item in top.GetSymbolGeometry():
            if not isinstance(item, GeometryInstance):
                continue
            t = outer.Multiply(item.Transform)
            angle = math.atan2(t.BasisX.Y, t.BasisX.X)
            layer = _layer(doc, item)
            raw = _block_name(doc, item)
            name = clean_name(raw) if raw else u"(block on layer %s)" % (layer or "?")
            found.append(Block(name, t.Origin.X, t.Origin.Y, normal_angle(angle), layer))
    return found


def read_blocks(doc, cad, view):
    """[Block] of the CAD's top-level block inserts. Reads the model
    geometry, or the view's geometry for a 'current view only' CAD."""
    blocks = []
    try:
        blocks = _inserts(doc, cad, None)
    except Exception:
        blocks = []
    if not blocks:
        blocks = _inserts(doc, cad, view)
    return blocks


# ---------------------------------------------------------------- fixtures

def light_types(doc):
    """{'Family : Type': FamilySymbol} of the lighting fixtures that can go
    on a ceiling or a level."""
    found = {}
    for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(LIGHT_CATEGORY):
        if placement_kind(symbol):
            found[type_label(symbol)] = symbol
    return found


def _existing(doc, level_z):
    """[(x, y)] of the lighting fixtures on this floor (any type)."""
    found = []
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance) \
            .OfCategory(LIGHT_CATEGORY).WhereElementIsNotElementType():
        point = getattr(instance.Location, "Point", None)
        if point is not None and level_z - RAY_START <= point.Z <= level_z + ABOVE_LEVEL:
            found.append((point.X, point.Y))
    return found


# ---------------------------------------------------------------- ceilings

class _Face(object):
    """Bottom face of a ceiling or slab, with what is needed to place on it."""

    def __init__(self, face, transform, link, element, reference):
        self.face = face
        self.ref = reference        # the face's reference in this model (link reference)
        self.transform = transform
        self.inverse = transform.Inverse
        self.link = link
        self.element = element
        self.normal = transform.OfVector(face.FaceNormal)
        self.origin = transform.OfPoint(face.Origin)
        xs, ys = [], []
        for loop in face.EdgeLoops:
            for edge in loop:
                for p in edge.Tessellate():
                    p = transform.OfPoint(p)
                    xs.append(p.X)
                    ys.append(p.Y)
        self.box = (min(xs), min(ys), max(xs), max(ys)) if xs else None

    def z_at(self, x, y):
        n, o = self.normal, self.origin
        return o.Z - (n.X * (x - o.X) + n.Y * (y - o.Y)) / n.Z

    def contains(self, x, y, z):
        b = self.box
        if not (b[0] - 0.01 <= x <= b[2] + 0.01 and b[1] - 0.01 <= y <= b[3] + 0.01):
            return False
        result = self.face.Project(self.inverse.OfPoint(XYZ(x, y, z)))
        return result is not None and result.Distance < 0.01



def _face_of(doc, reference):
    """(face, transform, link, element) of a ray hit's reference, or None."""
    linked = _id_int(reference.LinkedElementId) != _id_int(ElementId.InvalidElementId)
    try:
        if not linked:
            element = doc.GetElement(reference.ElementId)
            return (element.GetGeometryObjectFromReference(reference), Transform.Identity,
                    None, element)
        link = doc.GetElement(reference.ElementId)
        link_doc = link.GetLinkDocument()
        inner = reference.CreateReferenceInLink()
        element = link_doc.GetElement(inner.ElementId)
        return (element.GetGeometryObjectFromReference(inner), link.GetTotalTransform(),
                link, element)
    except Exception:
        return None


class CachedFinder(object):
    """Ceiling (or slab, where there is no ceiling) above points of a floor:
    the detector tool's rays, plus a memory of the ceiling faces hit."""

    def __init__(self, doc, view, level_z):
        self.doc = doc
        self.level_z = level_z
        self.finder = CeilingFinder(doc, view)
        self.cells = {}
        self.rays = 0

    def _remember(self, hit):
        found = _face_of(self.doc, hit.reference)
        if found is None or not isinstance(found[0], PlanarFace):
            return
        face, transform, link, element = found
        try:
            item = _Face(face, transform, link, element, hit.reference)
        except Exception:
            return
        if item.box is None or abs(item.normal.Z) < 1e-6:
            return
        b = item.box
        for i in range(int(math.floor(b[0] / CELL)), int(math.floor(b[2] / CELL)) + 1):
            for j in range(int(math.floor(b[1] / CELL)), int(math.floor(b[3] / CELL)) + 1):
                self.cells.setdefault((i, j), []).append(item)

    def _cached(self, x, y):
        best = None
        z0 = self.level_z
        for item in self.cells.get((int(math.floor(x / CELL)), int(math.floor(y / CELL))), ()):
            z = item.z_at(x, y)
            if z0 + RAY_START <= z <= z0 + ABOVE_LEVEL and (best is None or z < best[1]) \
                    and item.contains(x, y, z):
                best = (item, z)
        return best

    def above(self, x, y):
        cached = self._cached(x, y)
        if cached is not None:
            item, z = cached
            element = item.link if item.link is not None else item.element
            return Hit(item.ref, XYZ(x, y, z), element, item.link is not None, True)
        self.rays += 1
        hit = self.finder.above(x, y, self.level_z)
        if hit is not None and hit.ceiling:
            self._remember(hit)
        return hit


def _spot(finder, kind, block, level, height):
    """Hit to place on, or (None, reason)."""
    hit = finder.above(block.x, block.y)
    if kind == LEVEL:
        # cannot be hosted: set at the ceiling's (or slab's) height, else the set height
        z = hit.point.Z if hit is not None else level.ProjectElevation + height
        return Hit(None, XYZ(block.x, block.y, z), None, False, hit is None or hit.ceiling), ""
    if hit is None:
        return None, "no ceiling or slab above"
    if kind == HOSTED:
        if not hit.ceiling:
            return None, "no ceiling above to host it"
        if hit.linked:
            return None, ("the ceiling is in a linked model; a ceiling-hosted family needs "
                          "the ceiling in this model (use a face-based family)")
    return hit, ""


def _set(instance, bip, value):
    p = instance.get_Parameter(bip)
    if p is not None and not p.IsReadOnly:
        p.Set(value)
        return True
    return False


def _below_slab(doc, instance, face_z, kind, level_z, signs):
    """A light made for a ceiling (its body goes up into the ceiling void)
    put on a bare slab ends up inside the slab: move it down, along its host
    face, until its top touches the slab's underside. It stays hosted.

    signs {type id: +1/-1}: which way the host offset moves it down, found
    on the first light of each type."""
    box = instance.get_BoundingBox(None)
    if box is None:
        return
    inside = box.Max.Z - face_z
    if inside <= 0.003:                     # ~1 mm: already below the slab
        return
    if kind == LEVEL:
        _set(instance, BuiltInParameter.INSTANCE_ELEVATION_PARAM, face_z - inside - level_z)
        return
    p = instance.get_Parameter(BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
    if p is None or p.IsReadOnly:
        return
    start = p.AsDouble()
    key = _id_int(instance.GetTypeId())
    if key not in signs:
        p.Set(start + inside)
        doc.Regenerate()
        moved = instance.get_BoundingBox(None)
        signs[key] = 1 if moved is None or moved.Max.Z <= face_z + 0.003 else -1
        if signs[key] == 1:
            return
    p.Set(start + signs[key] * inside)


def place_lights(doc, level, jobs, height_mm, tolerance_mm, title):
    """Place the lights in one undo.

    jobs: [(block name, [Block], 'Family : Type', FamilySymbol)].
    Returns ([Result], [new ElementId], [(step, seconds)])."""
    height = height_mm / MM_PER_FOOT
    tol = tolerance_mm / MM_PER_FOOT
    level_z = level.ProjectElevation
    results, placed_ids, timings = [], [], []
    started = time.time()
    group = TransactionGroup(doc, title)
    group.Start()
    t = Transaction(doc, "CAD Lights ray view")
    t.Start()
    view = _ray_view(doc)
    t.Commit()
    finder = CachedFinder(doc, view, level_z)
    existing = _existing(doc, level_z)
    on_slab = []                # (instance, slab underside z, kind)
    t = Transaction(doc, title)
    t.Start()
    try:
        for name, blocks, label, symbol in jobs:
            result = Result(name, label)
            results.append(result)
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            kind = placement_kind(symbol)
            result.kind = kind
            new, already = split_spots(blocks, existing, tol)
            result.already = len(already)
            for block in new:
                hit, reason = _spot(finder, kind, block, level, height)
                if hit is None:
                    result.fail(reason)
                    continue
                direction = XYZ(math.cos(block.angle), math.sin(block.angle), 0)
                try:
                    instance = _place(doc, symbol, kind, hit, direction, level, block.angle)
                except Exception as err:
                    result.fail(u"%s" % err)
                    continue
                placed_ids.append(instance.Id)
                existing.append((block.x, block.y))
                result.placed += 1
                if kind != HOSTED and not hit.ceiling:
                    result.on_slab += 1
                    on_slab.append((instance, hit.point.Z, kind))
        if on_slab:
            doc.Regenerate()
            signs = {}
            for instance, face_z, kind in on_slab:
                _below_slab(doc, instance, face_z, kind, level_z, signs)
        doc.Delete(view.Id)
        t.Commit()
        group.Assimilate()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
    timings.append(("place (%d ceiling searches)" % finder.rays, time.time() - started))
    return results, placed_ids, timings
