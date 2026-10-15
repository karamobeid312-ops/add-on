# -*- coding: utf-8 -*-
"""Adding the missing FCU sockets: one on the underside of the slab above
each linked FCU that has none (slab in this model or a link).

The slabs (floors and roofs) over the FCUs are read once, then each FCU is
a quick lookup: the lowest downward face above the FCU. A face-based socket
is placed on that face (a link face too); a level-based one is set at its
height without a host. Ceiling-hosted families cannot go on a slab.
"""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, FamilyInstance, FamilySymbol, FilteredElementCollector, GeometryInstance,
    Level, Options, PlanarFace, Solid, Transaction, Transform, XYZ,
)

from firealarm.revit_fa import FACE, LEVEL, Hit, _place, linked_models, placement_kind, \
    type_label
from fcupower.revit_fcu import FEET, family_name

SLAB_CATEGORIES = (BuiltInCategory.OST_Floors, BuiltInCategory.OST_Roofs)
ABOVE = 6.0 / FEET              # how high above the FCU the slab may be
CELL = 10.0                     # ft, plan grid of the face index


def socket_types(doc, family_names):
    """{'Family : Type': FamilySymbol} of the ticked families' types that
    can go on a slab (face-based or level-based)."""
    found = {}
    names = set(family_names)
    for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
        try:
            if symbol.FamilyName not in names:
                continue
        except Exception:
            continue
        if placement_kind(symbol) in (FACE, LEVEL):
            found[type_label(symbol)] = symbol
    return found


def most_used(doc, labels, family_names):
    """The socket type placed most often in the ticked families."""
    counts = {}
    names = set(family_names)
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance) \
            .WhereElementIsNotElementType():
        if family_name(instance) in names:
            try:
                label = type_label(instance.Symbol)
            except Exception:
                continue
            counts[label] = counts.get(label, 0) + 1
    usable = [l for l in labels if l in counts]
    return max(usable, key=lambda l: counts[l]) if usable else (sorted(labels)[0] if labels else None)


class _Face(object):
    def __init__(self, face, transform, link, element, reference):
        self.face = face
        self.ref = reference
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


def _down_faces(element, options):
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


class SlabFinder(object):
    """Undersides of the slabs over some points, read once."""

    def __init__(self, doc, points):
        self.cells = {}
        self.faces = 0
        pad = 3.0
        x0 = min(p[0] for p in points) - pad
        y0 = min(p[1] for p in points) - pad
        x1 = max(p[0] for p in points) + pad
        y1 = max(p[1] for p in points) + pad
        z0 = min(p[2] for p in points)
        z1 = max(p[2] for p in points) + ABOVE
        options = Options()
        options.ComputeReferences = True
        sources = [(None, doc, Transform.Identity)] + \
            [(link, link_doc, link.GetTotalTransform()) for link, link_doc in linked_models(doc)]
        for link, source, transform in sources:
            for bic in SLAB_CATEGORIES:
                for element in FilteredElementCollector(source).OfCategory(bic) \
                        .WhereElementIsNotElementType():
                    try:
                        box = element.get_BoundingBox(None)
                        if box is None:
                            continue
                        lo, hi = transform.OfPoint(box.Min), transform.OfPoint(box.Max)
                        if max(lo.Z, hi.Z) < z0 or min(lo.Z, hi.Z) > z1:
                            continue
                        if max(lo.X, hi.X) < x0 or min(lo.X, hi.X) > x1 or \
                                max(lo.Y, hi.Y) < y0 or min(lo.Y, hi.Y) > y1:
                            continue
                        for face in list(_down_faces(element, options)):
                            ref = face.Reference
                            if ref is None:
                                continue
                            if link is not None:
                                ref = ref.CreateLinkReference(link)
                            item = _Face(face, transform, link, element, ref)
                            if item.box is not None:
                                self._bucket(item)
                                self.faces += 1
                    except Exception:
                        continue

    def _bucket(self, item):
        b = item.box
        for i in range(int(math.floor(b[0] / CELL)), int(math.floor(b[2] / CELL)) + 1):
            for j in range(int(math.floor(b[1] / CELL)), int(math.floor(b[3] / CELL)) + 1):
                self.cells.setdefault((i, j), []).append(item)

    def above(self, x, y, z):
        """Hit on the lowest slab underside above (x, y, z), or None."""
        best = None
        for item in self.cells.get((int(math.floor(x / CELL)), int(math.floor(y / CELL))), ()):
            fz = item.z_at(x, y)
            if z - 0.05 <= fz <= z + ABOVE and (best is None or fz < best[1]) \
                    and item.contains(x, y, fz):
                best = (item, fz)
        if best is None:
            return None
        item, fz = best
        element = item.link if item.link is not None else item.element
        return Hit(item.ref, XYZ(x, y, fz), element, item.link is not None, False)


def _level_below(levels, z):
    below = [l for l in levels if l.ProjectElevation <= z + 0.01]
    return max(below, key=lambda l: l.ProjectElevation) if below else \
        (min(levels, key=lambda l: l.ProjectElevation) if levels else None)


def add_sockets(doc, units, symbol, title="FCU sockets on slab"):
    """Place `symbol` on the slab above each unit (x, y, z, tag), in one
    undo. Returns (placed, [failures])."""
    kind = placement_kind(symbol)
    if kind not in (FACE, LEVEL):
        return 0, [u"%s cannot go on a slab (%s family)" % (type_label(symbol), kind or u"this")]
    finder = SlabFinder(doc, units)
    levels = list(FilteredElementCollector(doc).OfClass(Level))
    placed, failed = 0, []
    t = Transaction(doc, title)
    t.Start()
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        for x, y, z, tag in units:
            hit = finder.above(x, y, z)
            if hit is None:
                failed.append(u"%s: no slab found above the FCU" % tag)
                continue
            try:
                _place(doc, symbol, kind, hit, XYZ.BasisX, _level_below(levels, hit.point.Z), 0.0)
            except Exception as error:
                failed.append(u"%s: %s" % (tag, error))
                continue
            placed += 1
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return placed, failed
