# -*- coding: utf-8 -*-
"""Revit side: read the block inserts of a linked or imported DWG and
place lighting fixtures on them.

The ceiling above each block is found the same way as for the fire alarm
detectors (firealarm.revit_fa): a ray shot up from the plan's level,
through this model and linked models. The fixture family can be
  face-based       placed on the ceiling face (ceiling here or in a link)
  ceiling-hosted   hosted by the ceiling (ceiling in this model only)
  level-based      placed at the height set in the window, above the level
Where there is no ceiling the face-based lights go on the slab above.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, FamilyInstance, FamilySymbol, FilteredElementCollector,
    GeometryInstance, ImportInstance, Options, Transaction, TransactionGroup, XYZ,
)

from cadlights.match import MM_PER_FOOT, Block, Result, clean_name, normal_angle, split_spots
from firealarm.revit_fa import (FACE, HOSTED, LEVEL, CeilingFinder, Hit, _place, _ray_view,
                                placement_kind, type_label)

LIGHT_CATEGORY = BuiltInCategory.OST_LightingFixtures
ABOVE_LEVEL = 25.0          # ft above the level where existing lights still count
RAY_START = 1.0             # ft above the level where the rays start (as in revit_fa)


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


def _spot(finder, kind, block, level, height):
    """Hit to place on, or (None, reason)."""
    if kind == LEVEL:
        point = XYZ(block.x, block.y, level.ProjectElevation + height)
        return Hit(None, point, None, False, True), ""
    hit = finder.above(block.x, block.y, level.ProjectElevation)
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
    Returns ([Result], [new ElementId])."""
    height = height_mm / MM_PER_FOOT
    tol = tolerance_mm / MM_PER_FOOT
    level_z = level.ProjectElevation
    results, placed_ids = [], []
    group = TransactionGroup(doc, title)
    group.Start()
    t = None
    try:
        t = Transaction(doc, "CAD Lights ray view")
        t.Start()
        view = _ray_view(doc)
        t.Commit()
        finder = CeilingFinder(doc, view)
        existing = _existing(doc, level_z)

        t = Transaction(doc, title)
        t.Start()
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
                if kind == FACE and not hit.ceiling:
                    result.on_slab += 1
        doc.Delete(view.Id)
        t.Commit()
        group.Assimilate()
    except Exception:
        if t is not None and t.HasStarted() and not t.HasEnded():
            t.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
    return results, placed_ids
