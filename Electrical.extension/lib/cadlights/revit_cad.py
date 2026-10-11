# -*- coding: utf-8 -*-
"""Revit side: read the block inserts of a linked or imported DWG and
place lighting fixtures on them.

The ceiling above each block is looked up in an index of the bottom faces
of the ceilings (and floors/roofs, for the slab) on this floor, in this
model and in linked models: read once, then each block is a quick
lookup. (Shooting a ray per block, as the fire alarm detectors do, was
far too slow for a whole floor of lights.) The fixture family can be
  face-based       placed on the ceiling face (ceiling here or in a link)
  ceiling-hosted   hosted by the ceiling (ceiling in this model only)
  level-based      placed at the height set in the window, above the level
Where there is no ceiling the face-based lights go on the slab above.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math
import time

from Autodesk.Revit.DB import (
    BuiltInCategory, FamilyInstance, FamilySymbol, FilteredElementCollector,
    GeometryInstance, ImportInstance, Options, PlanarFace, Solid, Transaction,
    Transform, XYZ,
)

from cadlights.match import MM_PER_FOOT, Block, Result, clean_name, normal_angle, split_spots
from firealarm.revit_fa import (FACE, HOSTED, LEVEL, Hit, _place, linked_models,
                                placement_kind, type_label)

LIGHT_CATEGORY = BuiltInCategory.OST_LightingFixtures
ABOVE_LEVEL = 25.0          # ft above the level where existing lights still count
RAY_START = 1.0             # ft above the level where a ceiling can start
SLAB_MIN = 5.0              # ft: floors/roofs lower than this are not the slab above
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


def _block_name(doc, geometry):
    """Raw name of the block a GeometryInstance is an insert of."""
    try:
        symbol = doc.GetElement(geometry.GetSymbolGeometryId().SymbolId)   # Revit 2023+
        if symbol is not None and symbol.Name:
            return symbol.Name
    except Exception:
        pass
    try:
        return geometry.Symbol.Name                                        # older Revit
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

    def __init__(self, face, transform, link, element):
        self.face = face
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

    def reference(self):
        ref = self.face.Reference
        return ref.CreateLinkReference(self.link) if self.link is not None else ref


def _bottom_faces(element, options):
    geometry = element.get_Geometry(options)
    if geometry is None:
        return
    items = []
    for obj in geometry:
        if isinstance(obj, GeometryInstance):
            items.extend(obj.GetInstanceGeometry())
        else:
            items.append(obj)
    for obj in items:
        if isinstance(obj, Solid) and obj.Faces.Size:
            for face in obj.Faces:
                if isinstance(face, PlanarFace) and face.FaceNormal.Z < -0.5:
                    yield face


class _FaceIndex(object):
    """Bottom faces of the elements of some categories between two heights,
    bucketed on a plan grid."""

    def __init__(self, sources, categories, z_low, z_high, extent):
        self.cells = {}
        options = Options()
        options.ComputeReferences = True
        x0, y0, x1, y1 = extent
        for link, source_doc, transform in sources:
            for bic in categories:
                for element in FilteredElementCollector(source_doc).OfCategory(bic) \
                        .WhereElementIsNotElementType():
                    box = element.get_BoundingBox(None)
                    if box is None:
                        continue
                    lo, hi = transform.OfPoint(box.Min), transform.OfPoint(box.Max)
                    if max(lo.Z, hi.Z) < z_low or min(lo.Z, hi.Z) > z_high:
                        continue
                    if max(lo.X, hi.X) < x0 or min(lo.X, hi.X) > x1 or \
                            max(lo.Y, hi.Y) < y0 or min(lo.Y, hi.Y) > y1:
                        continue
                    try:
                        faces = list(_bottom_faces(element, options))
                    except Exception:
                        continue
                    for face in faces:
                        if face.Reference is None:
                            continue
                        item = _Face(face, transform, link, element)
                        if item.box is not None:
                            self._add(item)

    def _add(self, item):
        b = item.box
        for i in range(int(math.floor(b[0] / CELL)), int(math.floor(b[2] / CELL)) + 1):
            for j in range(int(math.floor(b[1] / CELL)), int(math.floor(b[3] / CELL)) + 1):
                self.cells.setdefault((i, j), []).append(item)

    def lowest(self, x, y, z_min, z_max):
        """(face, z) of the lowest face over (x, y) between the heights."""
        best = None
        for item in self.cells.get((int(math.floor(x / CELL)), int(math.floor(y / CELL))), ()):
            z = item.z_at(x, y)
            if z_min <= z <= z_max and (best is None or z < best[1]) and item.contains(x, y, z):
                best = (item, z)
        return best


class CeilingIndex(object):
    """Ceiling (or slab, where there is no ceiling) above points of a floor."""

    def __init__(self, doc, level_z, blocks):
        sources = [(None, doc, Transform.Identity)] + \
            [(link, link_doc, link.GetTotalTransform()) for link, link_doc in linked_models(doc)]
        pad = 5.0
        extent = (min(b.x for b in blocks) - pad, min(b.y for b in blocks) - pad,
                  max(b.x for b in blocks) + pad, max(b.y for b in blocks) + pad)
        self.level_z = level_z
        top = level_z + ABOVE_LEVEL
        self.ceilings = _FaceIndex(sources, (BuiltInCategory.OST_Ceilings,),
                                   level_z + RAY_START, top, extent)
        self.slabs = _FaceIndex(sources, (BuiltInCategory.OST_Floors, BuiltInCategory.OST_Roofs),
                                level_z + SLAB_MIN, top, extent)

    def above(self, x, y):
        z0 = self.level_z
        slab = self.slabs.lowest(x, y, z0 + SLAB_MIN, z0 + ABOVE_LEVEL)
        z_top = slab[1] + 1e-6 if slab is not None else z0 + ABOVE_LEVEL
        ceiling = self.ceilings.lowest(x, y, z0 + RAY_START, z_top)
        found, on_ceiling = (ceiling, True) if ceiling is not None else (slab, False)
        if found is None:
            return None
        item, z = found
        element = item.element if item.link is None else item.link
        return Hit(item.reference(), XYZ(x, y, z), element, item.link is not None, on_ceiling)


def _spot(index, kind, block, level, height):
    """Hit to place on, or (None, reason)."""
    if kind == LEVEL:
        point = XYZ(block.x, block.y, level.ProjectElevation + height)
        return Hit(None, point, None, False, True), ""
    hit = index.above(block.x, block.y)
    if hit is None:
        return None, "no ceiling or slab above"
    if kind == HOSTED:
        if not hit.ceiling:
            return None, "no ceiling above to host it"
        if hit.linked:
            return None, ("the ceiling is in a linked model; a ceiling-hosted family needs "
                          "the ceiling in this model (use a face-based family)")
    return hit, ""


def place_lights(doc, level, jobs, height_mm, tolerance_mm, title):
    """Place the lights in one undo.

    jobs: [(block name, [Block], 'Family : Type', FamilySymbol)].
    Returns ([Result], [new ElementId], [(step, seconds)])."""
    height = height_mm / MM_PER_FOOT
    tol = tolerance_mm / MM_PER_FOOT
    level_z = level.ProjectElevation
    results, placed_ids, timings = [], [], []
    started = time.time()
    index = None
    if any(placement_kind(symbol) != LEVEL for _, _, _, symbol in jobs):
        index = CeilingIndex(doc, level_z, [b for _, blocks, _, _ in jobs for b in blocks])
    timings.append(("find ceilings", time.time() - started))
    existing = _existing(doc, level_z)
    started = time.time()
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
            new, already = split_spots(blocks, existing, tol)
            result.already = len(already)
            for block in new:
                hit, reason = _spot(index, kind, block, level, height)
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
                if kind == FACE and not hit.ceiling:
                    result.on_slab += 1
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    timings.append(("place", time.time() - started))
    return results, placed_ids, timings
    return results, placed_ids
