# -*- coding: utf-8 -*-
"""Revit side: fixtures on walls read and measured against their wall.

A fixture is a family instance. Face-based families (out of the face
they are on: their Z axis) and wall-hosted families are checked when
their host is a wall, in this model or in a linked model. Each side face
of the wall (HostObjectUtils.GetSideFaces) is measured from the
fixture's insertion point and from the points of its 3D geometry, in
the wall's own coordinates (the link's, for a linked wall).

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, ElementMulticategoryFilter, FamilyInstance,
    FamilyPlacementType, FilteredElementCollector, GeometryInstance, HostObjectUtils, Level,
    Mesh, Options, PlanarFace, ReferencePlane, RevitLinkInstance, ShellLayerType, SketchPlane,
    Solid, ViewDetailLevel,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from firealarm.revit_fa import type_label
from wallcheck.check import (
    FLAT, LINK_MISSING, NO_HOST, NOT_WALL, OTHER_HOST, UNHOSTED, WALL, Fixture, Side,
)

M_PER_FOOT = 0.3048
FLAT_Z = 0.5            # a face-based fixture whose Z rises more than this is on a ceiling or floor
MAX_POINTS = 4000       # points of a fixture's geometry measured, at most

# Categories taken for "All": devices and fixtures that go on walls.
CATEGORIES = (
    BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_SecurityDevices,
    BuiltInCategory.OST_NurseCallDevices, BuiltInCategory.OST_TelephoneDevices,
)

_WALL = int(BuiltInCategory.OST_Walls)
_FLAT_HOSTS = set(int(bic) for bic in (
    BuiltInCategory.OST_Floors, BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_Roofs))


def id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _category(element):
    try:
        return id_int(element.Category.Id)
    except Exception:
        return None


def is_fixture(element):
    """A family instance placed at a point, not nested in another family."""
    return (isinstance(element, FamilyInstance) and element.SuperComponent is None and
            getattr(getattr(element, "Location", None), "Point", None) is not None)


# ---------------------------------------------------------------- choosing

def model_fixtures(doc, view=None):
    """Fixtures of CATEGORIES in the model, or shown in the view."""
    categories = List[BuiltInCategory]()
    for bic in CATEGORIES:
        categories.Add(bic)
    collector = FilteredElementCollector(doc, view.Id) if view is not None \
        else FilteredElementCollector(doc)
    found = collector.OfClass(FamilyInstance).WherePasses(ElementMulticategoryFilter(categories))
    return [e for e in found if is_fixture(e)]


def selection(uidoc):
    doc = uidoc.Document
    elements = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    return [e for e in elements if e is not None and is_fixture(e)]


class _FixtureFilter(ISelectionFilter):
    __namespace__ = "ElectricalWallCheck"       # needed by the CPython engine

    def AllowElement(self, element):
        return is_fixture(element)

    def AllowReference(self, reference, position):
        return False


def pick_fixtures(uidoc):
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _FixtureFilter(), "Select the fixtures, then click Finish")
    except OperationCanceledException:
        return []
    doc = uidoc.Document
    return [doc.GetElement(r.ElementId) for r in refs]


# ---------------------------------------------------------------- reading

def _level_name(instance):
    doc = instance.Document
    ids = [instance.LevelId]
    for bip in (BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
                BuiltInParameter.FAMILY_LEVEL_PARAM):
        try:
            ids.append(instance.get_Parameter(bip).AsElementId())
        except Exception:
            pass
    for level_id in ids:
        try:
            if level_id is not None and id_int(level_id) != id_int(ElementId.InvalidElementId):
                return doc.GetElement(level_id).Name
        except Exception:
            pass
    return ""


def _host(instance):
    """(host kind, wall, transform of the wall's model or None, out axis or None).
    The out axis is the face-based fixture's Z: out of the face it is on."""
    try:
        placement = instance.Symbol.Family.FamilyPlacementType
    except Exception:
        return UNHOSTED, None, None, None
    out = None
    if placement == FamilyPlacementType.WorkPlaneBased:
        out = instance.GetTransform().BasisZ
        if abs(out.Z) > FLAT_Z:
            return FLAT, None, None, None
    elif placement != FamilyPlacementType.OneLevelBasedHosted:
        return UNHOSTED, None, None, None
    host = instance.Host
    if host is None:
        return NO_HOST, None, None, None
    transform = None
    if isinstance(host, RevitLinkInstance):
        link_doc = host.GetLinkDocument()
        face = instance.HostFace
        wall = None
        if link_doc is not None and face is not None:
            try:
                wall = link_doc.GetElement(face.LinkedElementId)
            except Exception:
                wall = None
        if wall is None:
            return LINK_MISSING, None, None, None
        transform, host = host.GetTotalTransform(), wall
    if isinstance(host, (Level, ReferencePlane, SketchPlane)):
        return NOT_WALL, None, None, None
    category = _category(host)
    if category == _WALL:
        return WALL, host, transform, out
    if category in _FLAT_HOSTS:
        return FLAT, None, None, None
    return OTHER_HOST, None, None, None


def _body_points(instance):
    """Points of the fixture's 3D geometry (its solids' edges, meshes)."""
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    points = []

    def walk(geometry):
        if geometry is None:
            return
        for item in geometry:
            if len(points) >= MAX_POINTS:
                return
            if isinstance(item, GeometryInstance):
                walk(item.GetInstanceGeometry())
            elif isinstance(item, Solid):
                if item.Volume <= 1e-9:
                    continue
                for edge in item.Edges:
                    points.extend(edge.Tessellate())
            elif isinstance(item, Mesh):
                points.extend(item.Vertices)

    try:
        walk(instance.get_Geometry(options))
    except Exception:
        return []
    return points[:MAX_POINTS]


def _side_faces(wall):
    faces = []
    for side in (ShellLayerType.Exterior, ShellLayerType.Interior):
        try:
            refs = list(HostObjectUtils.GetSideFaces(wall, side))
        except Exception:
            continue
        for ref in refs:
            try:
                face = wall.GetGeometryObjectFromReference(ref)
            except Exception:
                face = None
            if face is not None:
                faces.append(face)
    return faces


def _measure(face, point, body, out, use_gap):
    """Side of one wall face, or None. point, body, out: in the wall's coordinates."""
    try:
        found = face.Project(point)
    except Exception:
        found = None
    on_face = found is not None
    try:
        if on_face:
            foot = found.XYZPoint
            normal = face.FaceNormal if isinstance(face, PlanarFace) \
                else face.ComputeNormal(found.UVPoint)
        elif isinstance(face, PlanarFace):
            foot, normal = face.Origin, face.FaceNormal
        else:
            return None
        normal = normal.Normalize()
    except Exception:
        return None
    gap = point.Subtract(foot).DotProduct(normal) * M_PER_FOOT if use_gap else None
    front = back = None
    if body:
        heights = [p.Subtract(foot).DotProduct(normal) for p in body]
        front, back = max(heights) * M_PER_FOOT, min(heights) * M_PER_FOOT
    square = out.Normalize().DotProduct(normal) if out is not None else None
    return Side(gap, on_face, front, back, square)


def read_fixture(instance):
    """The Fixture of a family instance, measured against its wall."""
    kind, wall, transform, out = _host(instance)
    try:
        category = instance.Category.Name
    except Exception:
        category = ""
    fixture = Fixture(instance.Id, type_label(instance.Symbol), category,
                      _level_name(instance), kind)
    if kind != WALL:
        return fixture
    point = instance.Location.Point
    body = _body_points(instance)
    if transform is not None:               # into the link's coordinates
        inverse = transform.Inverse
        point = inverse.OfPoint(point)
        body = [inverse.OfPoint(p) for p in body]
        out = inverse.OfVector(out) if out is not None else None
    for face in _side_faces(wall):
        side = _measure(face, point, body, out, use_gap=out is not None)
        if side is not None:
            fixture.sides.append(side)
    return fixture


def read_fixtures(instances):
    return [read_fixture(i) for i in instances]
