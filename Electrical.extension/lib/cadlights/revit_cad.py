# -*- coding: utf-8 -*-
"""Revit side: read the block inserts of a linked or imported DWG and
place lighting fixtures on them.

The ceiling above each block is found like the fire alarm detectors do it
(firealarm.revit_fa.CeilingFinder, one search per ray here): a ray shot up from the plan's level
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
    ElementId, GeometryInstance, ImportInstance, Options, PlanarFace, Solid, Transaction,
    TransactionGroup, Transform, XYZ,
)

from cadlights.match import MM_PER_FOOT, Block, Result, clean_name, normal_angle, split_spots
from firealarm.revit_fa import (HOSTED, LEVEL, Hit, _place, _ray_view,
                                linked_models, placement_kind, type_label)

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
    """[(x, y, element id)] of the lighting fixtures of this model on this
    floor (any type). Lights in linked models are not counted."""
    found = []
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance) \
            .OfCategory(LIGHT_CATEGORY).WhereElementIsNotElementType():
        point = getattr(instance.Location, "Point", None)
        if point is not None and level_z - RAY_START <= point.Z <= level_z + ABOVE_LEVEL:
            found.append((point.X, point.Y, _id_int(instance.Id)))
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


def _flat_faces(element, options, down_only):
    """Planar faces of the element that face down (or up too: a basic
    ceiling is a sheet whose one face may point either way)."""
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
                if isinstance(face, PlanarFace):
                    nz = face.FaceNormal.Z
                    if nz < -0.5 or (not down_only and nz > 0.5):
                        yield face


class _FaceIndex(object):
    """Flat faces of the elements of some categories between two heights,
    in this model and links, bucketed on a plan grid. Read once."""

    def __init__(self, sources, categories, z_low, z_high, extent, down_only):
        self.cells = {}
        self.elements = 0           # elements found near the lights
        self.faces = 0
        self.errors = {}            # message -> count
        options = Options()
        options.ComputeReferences = True
        x0, y0, x1, y1 = extent
        for link, source_doc, transform in sources:
            for bic in categories:
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
                        self.elements += 1
                        for face in list(_flat_faces(element, options, down_only)):
                            ref = face.Reference
                            if ref is None:
                                self._error("face without reference")
                                continue
                            if link is not None:
                                ref = ref.CreateLinkReference(link)
                            item = _Face(face, transform, link, element, ref)
                            if item.box is not None:
                                _bucket(self.cells, item)
                                self.faces += 1
                    except Exception as err:
                        self._error(u"%s" % err)

    def _error(self, message):
        self.errors[message] = self.errors.get(message, 0) + 1

    def note(self, what):
        text = u"%s read: %d faces from %d elements" % (what, self.faces, self.elements)
        for message, count in sorted(self.errors.items())[:3]:
            text += u"; %d x %s" % (count, message[:120])
        return text

    def lowest(self, x, y, z_min, z_max):
        """(face, z) of the lowest face over (x, y) between the heights."""
        return _lowest(self.cells, x, y, z_min, z_max)


def _bucket(cells, item):
    b = item.box
    for i in range(int(math.floor(b[0] / CELL)), int(math.floor(b[2] / CELL)) + 1):
        for j in range(int(math.floor(b[1] / CELL)), int(math.floor(b[3] / CELL)) + 1):
            cells.setdefault((i, j), []).append(item)


def _lowest(cells, x, y, z_min, z_max):
    best = None
    for item in cells.get((int(math.floor(x / CELL)), int(math.floor(y / CELL))), ()):
        z = item.z_at(x, y)
        if z_min <= z <= z_max and (best is None or z < best[1]) and item.contains(x, y, z):
            best = (item, z)
    return best



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


class _OneRay(object):
    """The detector tool's ceiling/slab choice with one ray per point
    (ceilings, floors and roofs in one search instead of two)."""

    def __init__(self, doc, view):
        from System.Collections.Generic import List
        from Autodesk.Revit.DB import (ElementMulticategoryFilter, FindReferenceTarget,
                                       ReferenceIntersector)
        self.doc = doc
        cats = List[BuiltInCategory]()
        for bic in (BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_Floors,
                    BuiltInCategory.OST_Roofs):
            cats.Add(bic)
        self.intersector = ReferenceIntersector(ElementMulticategoryFilter(cats),
                                                FindReferenceTarget.Face, view)
        self.intersector.FindReferencesInRevitLinks = True
        self.ceiling_cat = _id_int(ElementId(BuiltInCategory.OST_Ceilings))
        self.link_docs = {}

    def _is_ceiling(self, reference):
        try:
            if _id_int(reference.LinkedElementId) == _id_int(ElementId.InvalidElementId):
                element = self.doc.GetElement(reference.ElementId)
            else:
                key = _id_int(reference.ElementId)
                if key not in self.link_docs:
                    self.link_docs[key] = self.doc.GetElement(reference.ElementId).GetLinkDocument()
                element = self.link_docs[key].GetElement(reference.LinkedElementId)
            return _id_int(element.Category.Id) == self.ceiling_cat
        except Exception:
            return False

    def above(self, x, y, floor_z):
        origin = XYZ(x, y, floor_z + RAY_START)
        ceiling = slab = None
        for found in self.intersector.Find(origin, XYZ.BasisZ):
            reference = found.GetReference()
            if self._is_ceiling(reference):
                if ceiling is None or found.Proximity < ceiling.Proximity:
                    ceiling = found
            elif found.Proximity >= SLAB_MIN - RAY_START and \
                    (slab is None or found.Proximity < slab.Proximity):
                slab = found
        if ceiling is not None and (slab is None or ceiling.Proximity <= slab.Proximity + 1e-6):
            found, on_ceiling = ceiling, True
        elif slab is not None:
            found, on_ceiling = slab, False
        else:
            return None
        reference = found.GetReference()
        point = reference.GlobalPoint or XYZ(x, y, origin.Z + found.Proximity)
        linked = _id_int(reference.LinkedElementId) != _id_int(ElementId.InvalidElementId)
        return Hit(reference, point, self.doc.GetElement(reference.ElementId), linked, on_ceiling)


class CachedFinder(object):
    """Ceiling (or slab, where there is no ceiling) above points of a floor.

    1. the ceilings and slabs of the floor are read once (fast lookups);
       a ceiling found there under the slab is used straight away;
    2. otherwise the detector tool's rays decide (ceiling first, then slab),
       and each ceiling face a ray hits is remembered for the next lights."""

    def __init__(self, doc, view, level_z, blocks):
        self.doc = doc
        self.level_z = level_z
        self.finder = _OneRay(doc, view)
        self.cells = {}             # ceiling faces found by rays
        self.rays = 0
        self.quick = 0
        sources = [(None, doc, Transform.Identity)] + \
            [(link, link_doc, link.GetTotalTransform()) for link, link_doc in linked_models(doc)]
        pad = 5.0
        extent = (min(b.x for b in blocks) - pad, min(b.y for b in blocks) - pad,
                  max(b.x for b in blocks) + pad, max(b.y for b in blocks) + pad)
        top = level_z + ABOVE_LEVEL
        self.ceilings = _FaceIndex(sources, (BuiltInCategory.OST_Ceilings,),
                                   level_z + RAY_START, top, extent, False)
        self.slabs = _FaceIndex(sources, (BuiltInCategory.OST_Floors, BuiltInCategory.OST_Roofs),
                                level_z + SLAB_MIN, top, extent, True)

    def _remember(self, hit):
        found = _face_of(self.doc, hit.reference)
        if found is None or not isinstance(found[0], PlanarFace):
            return
        face, transform, link, element = found
        try:
            item = _Face(face, transform, link, element, hit.reference)
        except Exception:
            return
        if item.box is not None and abs(item.normal.Z) > 1e-6:
            _bucket(self.cells, item)

    @staticmethod
    def _hit(found, x, y):
        item, z = found
        element = item.link if item.link is not None else item.element
        return Hit(item.ref, XYZ(x, y, z), element, item.link is not None, True)

    def above(self, x, y):
        z0 = self.level_z
        slab = self.slabs.lowest(x, y, z0 + SLAB_MIN, z0 + ABOVE_LEVEL)
        z_top = slab[1] + 1e-6 if slab is not None else z0 + ABOVE_LEVEL
        found = self.ceilings.lowest(x, y, z0 + RAY_START, z_top) or \
            _lowest(self.cells, x, y, z0 + RAY_START, z_top)
        if found is not None:
            self.quick += 1
            return self._hit(found, x, y)
        self.rays += 1
        hit = self.finder.above(x, y, z0)
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
    Returns ([Result], [new ElementId], [(step, seconds)], [note])."""
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
    finder = CachedFinder(doc, view, level_z, [b for _, blocks, _, _ in jobs for b in blocks])
    timings.append(("read ceilings", time.time() - started))
    started = time.time()
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
            new, already, duplicates = split_spots(blocks, existing, tol)
            result.already = len(already)
            result.blockers = sorted(set(tag for _, tag in already if tag is not None))
            result.duplicates = len(duplicates)
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
                existing.append((block.x, block.y, _id_int(instance.Id)))
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
    timings.append(("place (%d quick, %d ray searches)" % (finder.quick, finder.rays),
                    time.time() - started))
    notes = [finder.ceilings.note("Ceilings"), finder.slabs.note("Slabs")]
    return results, placed_ids, timings, notes
