# -*- coding: utf-8 -*-
"""Revit side: selected spaces -> detector points -> detectors on the
ceiling above each point.

The ceiling is found with a ray shot straight up from each point, through
this model and linked models. The detector family can be
  face-based       placed on the ceiling face (ceiling here or in a link)
  ceiling-hosted   hosted by the ceiling (ceiling in this model only)
  level-based      placed at ceiling height, as an offset from the level
Where there is no ceiling below the slab (floor or roof) above a point,
the detector goes on the slab.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementCategoryFilter, ElementId,
    ElementMulticategoryFilter, ElementTransformUtils, FamilyInstance,
    FamilyPlacementType, FamilySymbol, FilteredElementCollector,
    FindReferenceTarget, Line, ReferenceIntersector,
    SpatialElementBoundaryLocation, SpatialElementBoundaryOptions,
    StorageType, Transaction, TransactionGroup, View3D, ViewFamily,
    ViewFamilyType, XYZ,
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from firealarm.layout import layout_detectors, point_in_loops

M_PER_FOOT = 0.3048
RAY_START = 1.0             # ft above the space's floor where the rays start
SLAB_MIN = 5.0              # ft: floors/roofs lower than this (stages, raised
                            # floors) are not the slab above

FACE, HOSTED, LEVEL = "face-based", "ceiling-hosted", "level-based"

# Categories offered for the detector type; the others only when the model
# has no Fire Alarm Devices loaded.
DETECTOR_CATEGORY = BuiltInCategory.OST_FireAlarmDevices
OTHER_CATEGORIES = (
    BuiltInCategory.OST_SecurityDevices, BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_NurseCallDevices,
    BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_GenericModel,
    BuiltInCategory.OST_SpecialityEquipment,
)


# ---------------------------------------------------------------- helpers

def _id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _param_text(element, bip):
    try:
        p = element.get_Parameter(bip)
    except Exception:
        return ""
    if p is None or not p.HasValue:
        return ""
    value = p.AsString() if p.StorageType == StorageType.String else p.AsValueString()
    return (value or "").strip()


_SPACE_CATEGORIES = (int(BuiltInCategory.OST_MEPSpaces), int(BuiltInCategory.OST_Rooms))


def is_space(element):
    """MEP space or room."""
    try:
        return _id_int(element.Category.Id) in _SPACE_CATEGORIES
    except Exception:
        return False


def space_label(space):
    number = _param_text(space, BuiltInParameter.ROOM_NUMBER)
    name = _param_text(space, BuiltInParameter.ROOM_NAME)
    return " ".join(p for p in (number, name) if p) or "Space id %s" % _id_int(space.Id)


# ---------------------------------------------------------------- selection

class _SpaceFilter(ISelectionFilter):
    __namespace__ = "FireAlarmDetectors"    # needed by the CPython engine

    def AllowElement(self, element):
        return is_space(element)

    def AllowReference(self, reference, position):
        return False


def selected_spaces(uidoc):
    doc = uidoc.Document
    elements = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    return [e for e in elements if e is not None and is_space(e)]


def pick_spaces(uidoc):
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _SpaceFilter(), "Select the spaces, then click Finish")
    except OperationCanceledException:
        return []
    doc = uidoc.Document
    return [doc.GetElement(r.ElementId) for r in refs]


# ---------------------------------------------------------------- detector types

def type_label(symbol):
    name = _param_text(symbol, BuiltInParameter.SYMBOL_NAME_PARAM) or \
        _param_text(symbol, BuiltInParameter.ALL_MODEL_TYPE_NAME)
    return u"%s : %s" % (symbol.FamilyName, name)


def detector_types(doc):
    """{'Family : Type': FamilySymbol}, Fire Alarm Devices (or, when there
    are none, other device and generic families)."""
    def collect(categories):
        found = {}
        for bic in categories:
            for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(bic):
                if placement_kind(symbol):
                    found[type_label(symbol)] = symbol
        return found
    return collect((DETECTOR_CATEGORY,)) or collect(OTHER_CATEGORIES)


def placement_kind(symbol):
    """FACE / HOSTED / LEVEL, or None for families that cannot go on a ceiling."""
    try:
        kind = symbol.Family.FamilyPlacementType
    except Exception:
        return None
    if kind == FamilyPlacementType.WorkPlaneBased:
        return FACE
    if kind == FamilyPlacementType.OneLevelBasedHosted:
        return HOSTED
    if kind == FamilyPlacementType.OneLevelBased:
        return LEVEL
    return None


# ---------------------------------------------------------------- spaces

def boundary_loops(space):
    """Outline and holes of the space (finish faces) in metres."""
    options = SpatialElementBoundaryOptions()
    options.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    loops = []
    for boundary in space.GetBoundarySegments(options) or []:
        points = []
        for segment in boundary:
            for p in list(segment.GetCurve().Tessellate())[:-1]:
                points.append((p.X * M_PER_FOOT, p.Y * M_PER_FOOT))
        if len(points) >= 3:
            loops.append(points)
    return loops


def _heights(doc, space):
    """Floor and top of the space (ft, model coordinates)."""
    box = space.get_BoundingBox(None)
    if box is not None:
        return box.Min.Z, box.Max.Z
    level = doc.GetElement(space.LevelId)
    z = level.ProjectElevation if level is not None else 0.0
    return z, z + 10.0


# ---------------------------------------------------------------- ceilings

def _ray_view(doc):
    """A plain 3D view for the rays: no template or section box, ceilings,
    slabs and links shown. Deleted again at the end."""
    view_type = [t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
                 if t.ViewFamily == ViewFamily.ThreeDimensional][0]
    view = View3D.CreateIsometric(doc, view_type.Id)
    try:
        view.ViewTemplateId = ElementId.InvalidElementId
    except Exception:
        pass
    try:
        view.IsSectionBoxActive = False
    except Exception:
        pass
    for bic in (BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_Floors,
                BuiltInCategory.OST_Roofs, BuiltInCategory.OST_RvtLinks):
        try:
            view.SetCategoryHidden(ElementId(bic), False)
        except Exception:
            pass
    return view


class Hit(object):
    """Face above a detector point."""

    def __init__(self, reference, point, element, linked, ceiling):
        self.reference = reference
        self.point = point          # XYZ on the face (ft)
        self.element = element      # the ceiling/slab, or the link instance
        self.linked = linked
        self.ceiling = ceiling      # False: slab above (no ceiling)


class CeilingFinder(object):

    def __init__(self, doc, view):
        self.doc = doc
        slabs = List[BuiltInCategory]()
        slabs.Add(BuiltInCategory.OST_Floors)
        slabs.Add(BuiltInCategory.OST_Roofs)
        self.ceilings = self._intersector(
            ElementCategoryFilter(BuiltInCategory.OST_Ceilings), view)
        self.slabs = self._intersector(ElementMulticategoryFilter(slabs), view)

    @staticmethod
    def _intersector(element_filter, view):
        intersector = ReferenceIntersector(element_filter, FindReferenceTarget.Face, view)
        intersector.FindReferencesInRevitLinks = True
        return intersector

    @staticmethod
    def _first(intersector, origin, min_distance):
        best = None
        for found in intersector.Find(origin, XYZ.BasisZ):
            if found.Proximity >= min_distance and \
                    (best is None or found.Proximity < best.Proximity):
                best = found
        return best

    def above(self, x, y, floor_z):
        """The ceiling above (x, y), or the slab when there is no ceiling
        below it (so an open room never picks up the next floor's ceiling)."""
        origin = XYZ(x, y, floor_z + RAY_START)
        ceiling = self._first(self.ceilings, origin, 0.0)
        slab = self._first(self.slabs, origin, SLAB_MIN - RAY_START)
        if ceiling is not None and (slab is None or ceiling.Proximity <= slab.Proximity + 1e-6):
            found, on_ceiling = ceiling, True
        elif slab is not None:
            found, on_ceiling = slab, False
        else:
            return None
        reference = found.GetReference()
        point = reference.GlobalPoint or XYZ(origin.X, origin.Y, origin.Z + found.Proximity)
        linked = _id_int(reference.LinkedElementId) != _id_int(ElementId.InvalidElementId)
        return Hit(reference, point, self.doc.GetElement(reference.ElementId), linked, on_ceiling)


# ---------------------------------------------------------------- placing

class SpacePlan(object):
    """What happens in one space."""

    def __init__(self, space):
        self.space = space
        self.label = space_label(space)
        self.problem = ""           # why nothing is placed
        self.layout = None
        self.spots = []             # [(x, y, Hit or None)] ft
        self.floor_z = 0.0
        self.level = None
        self.existing = []          # detectors of the same type already inside
        self.placed = []            # new ElementIds
        self.failed = []            # messages, one per detector not placed

    def ceiling_heights(self):
        """Heights of the hits above the floor (m)."""
        return [(hit.point.Z - self.floor_z) * M_PER_FOOT
                for _, _, hit in self.spots if hit is not None]


def _existing(doc, symbol):
    found = []
    type_id = _id_int(symbol.Id)
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance) \
            .OfCategoryId(symbol.Category.Id):
        if _id_int(instance.GetTypeId()) != type_id:
            continue
        point = getattr(instance.Location, "Point", None)
        if point is not None:
            found.append((instance.Id, point))
    return found


def _plan(doc, space, spacing, clearance, finder, existing):
    plan = SpacePlan(space)
    if space.Area <= 0:
        plan.problem = "not placed or not enclosed"
        return plan
    loops = boundary_loops(space)
    if not loops:
        plan.problem = "no boundary"
        return plan
    plan.floor_z, top_z = _heights(doc, space)
    plan.level = doc.GetElement(space.LevelId)
    plan.layout = layout_detectors(loops, spacing, clearance)
    for x, y in plan.layout.points:
        xf, yf = x / M_PER_FOOT, y / M_PER_FOOT
        plan.spots.append((xf, yf, finder.above(xf, yf, plan.floor_z)))
    top_z = max([top_z] + [hit.point.Z for _, _, hit in plan.spots if hit is not None])
    plan.existing = [
        element_id for element_id, p in existing
        if plan.floor_z - RAY_START <= p.Z <= top_z + RAY_START
        and point_in_loops(p.X * M_PER_FOOT, p.Y * M_PER_FOOT, loops)]
    return plan


def _set_offset(instance, offset):
    for bip in (BuiltInParameter.INSTANCE_ELEVATION_PARAM,
                BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM):
        p = instance.get_Parameter(bip)
        if p is not None and not p.IsReadOnly:
            p.Set(offset)
            return


def _place(doc, symbol, kind, hit, direction, level, angle):
    if kind == FACE:
        return doc.Create.NewFamilyInstance(hit.reference, hit.point, direction, symbol)
    if kind == HOSTED:
        if not hit.ceiling:
            raise ValueError("no ceiling above to host it")
        if hit.linked:
            raise ValueError("the ceiling is in a linked model; a ceiling-hosted family "
                             "needs the ceiling in this model (use a face-based family)")
        return doc.Create.NewFamilyInstance(hit.point, symbol, direction, hit.element,
                                            StructuralType.NonStructural)
    instance = doc.Create.NewFamilyInstance(hit.point, symbol, level, StructuralType.NonStructural)
    _set_offset(instance, hit.point.Z - level.ProjectElevation)
    if abs(angle) > 1e-9:
        axis = Line.CreateBound(hit.point, hit.point + XYZ.BasisZ)
        ElementTransformUtils.RotateElement(doc, instance.Id, axis, angle)
    return instance


def place_detectors(doc, spaces, symbol, spacing, clearance, title, ask_replace):
    """Lay out and place detectors of `symbol` in `spaces` (one undo).

    ask_replace(count, space_count) is called when detectors of this type
    are already in some of the spaces: True replaces them, False keeps
    them, None cancels. Returns the SpacePlans, or None when cancelled."""
    kind = placement_kind(symbol)
    group = TransactionGroup(doc, title)
    group.Start()
    t = None
    try:
        t = Transaction(doc, "Detector placement view")
        t.Start()
        view = _ray_view(doc)
        t.Commit()

        finder = CeilingFinder(doc, view)
        existing = _existing(doc, symbol)
        plans = [_plan(doc, s, spacing, clearance, finder, existing) for s in spaces]

        old = [i for plan in plans for i in plan.existing]
        replace = False
        if old:
            replace = ask_replace(len(old), len([p for p in plans if p.existing]))
            if replace is None:
                group.RollBack()
                return None

        t = Transaction(doc, title)
        t.Start()
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        if replace:
            doc.Delete(List[ElementId](old))
        for plan in plans:
            if plan.layout is None:
                continue
            angle = plan.layout.angle
            direction = XYZ(math.cos(angle), math.sin(angle), 0)
            for _, _, hit in plan.spots:
                if hit is None:
                    plan.failed.append("no ceiling or slab above")
                    continue
                try:
                    instance = _place(doc, symbol, kind, hit, direction, plan.level, angle)
                    plan.placed.append(instance.Id)
                except Exception as err:
                    plan.failed.append(u"%s" % err)
        doc.Delete(view.Id)
        t.Commit()
        group.Assimilate()
    except Exception:
        if t is not None and t.HasStarted() and not t.HasEnded():
            t.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
    return plans
