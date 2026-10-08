# -*- coding: utf-8 -*-
"""Revit side: what is in a tray's way read from the model and its links,
new trays drawn along a routed path, and existing trays rerouted.

Lengths cross into traycoord.route in metres, in the host model's
coordinates (a linked element is moved by its link's transform).

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

from Autodesk.Revit.DB import (
    BoundingBoxIntersectsFilter, BuiltInCategory, BuiltInParameter, ElementId,
    ElementMulticategoryFilter, FilteredElementCollector, GeometryInstance, Level, Line,
    LocationCurve, Mesh, Options, Outline, Plane, RevitLinkInstance, SketchPlane, Solid,
    ViewDetailLevel, ViewPlan, XYZ,
)
from Autodesk.Revit.DB.Electrical import CableTray, CableTrayType
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from traycoord.route import box_obstacle, linear_obstacles

M_PER_FOOT = 0.3048
MAX_POINTS = 2000       # points of an element's geometry read, at most
REACH = 3.0             # m, how far beside the path obstacles are read (for dodges round)
_WALL = int(BuiltInCategory.OST_Walls)


def id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _m(xyz):
    return (xyz.X * M_PER_FOOT, xyz.Y * M_PER_FOOT, xyz.Z * M_PER_FOOT)


def _xyz(point):
    return XYZ(point[0] / M_PER_FOOT, point[1] / M_PER_FOOT, point[2] / M_PER_FOOT)


def label(element):
    try:
        category = element.Category.Name
    except Exception:
        category = ""
    try:
        name = element.Document.GetElement(element.GetTypeId()).get_Parameter(
            BuiltInParameter.SYMBOL_FAMILY_AND_TYPE_NAMES_PARAM).AsString()
    except Exception:
        name = None
    return u"%s : %s" % (category, name) if name else category


# ---------------------------------------------------------------- views and levels

def is_plan(view):
    return isinstance(view, ViewPlan) and view.GenLevel is not None


def levels(doc):
    return sorted(FilteredElementCollector(doc).OfClass(Level),
                  key=lambda level: level.ProjectElevation)


def limits(doc, z, headroom, slab):
    """(lowest, highest) in metres the tray may go at middle elevation z
    (metres): headroom above the level at or under it, slab under the
    level above it. None where there is no such level."""
    bottom = top = None
    for level in levels(doc):
        elevation = level.ProjectElevation * M_PER_FOOT
        if elevation <= z + 1e-6:
            bottom = elevation + headroom
        elif top is None:
            top = elevation - slab
    return bottom, top


def ensure_work_plane(doc, view):
    """Points are picked on the view's level: give the plan a work plane there."""
    if view.SketchPlane is not None:
        return
    origin = XYZ(0, 0, view.GenLevel.ProjectElevation)
    view.SketchPlane = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, origin))


def pick_path(uidoc, z):
    """Points clicked in the plan, at middle elevation z (metres), until Esc."""
    points = []
    while True:
        prompt = ("Click where the tray starts" if not points else
                  "Click the next corner or the end of the tray, Esc to finish")
        try:
            picked = uidoc.Selection.PickPoint(prompt)
        except OperationCanceledException:
            return points
        point = (picked.X * M_PER_FOOT, picked.Y * M_PER_FOOT, z)
        if points and abs(point[0] - points[-1][0]) + abs(point[1] - points[-1][1]) < 0.01:
            continue
        points.append(point)


def tray_types(doc):
    """{name: CableTrayType}"""
    found = {}
    for t in FilteredElementCollector(doc).OfClass(CableTrayType):
        try:
            found[t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()] = t
        except Exception:
            pass
    return found


# ---------------------------------------------------------------- obstacles

def _points(element, transform):
    """Points of the element's 3D geometry, in the host's coordinates (feet)."""
    options = Options()
    options.DetailLevel = ViewDetailLevel.Coarse
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
        walk(element.get_Geometry(options))
    except Exception:
        points = []
    if not points:
        box = element.get_BoundingBox(None)
        if box is None:
            return []
        points = [box.Min, box.Max]
    points = points[:MAX_POINTS]
    if transform is not None:
        points = [transform.OfPoint(p) for p in points]
    return points


def _obstacles(element, key, transform, suffix):
    points = _points(element, transform)
    if not points:
        return []
    metres = [_m(p) for p in points]
    name = label(element) + suffix
    try:
        wall = id_int(element.Category.Id) == _WALL
    except Exception:
        wall = False
    location = getattr(element, "Location", None)
    curve = location.Curve if isinstance(location, LocationCurve) else None
    if isinstance(curve, Line):
        a, b = curve.GetEndPoint(0), curve.GetEndPoint(1)
        if transform is not None:
            a, b = transform.OfPoint(a), transform.OfPoint(b)
        found = linear_obstacles(key, name, _m(a), _m(b), metres, wall=wall)
        if found:
            return found
    return [box_obstacle(key, name, metres, wall=wall)]


def _collector(doc, categories, low, high):
    """Elements of the categories whose box meets the box low-high (feet)."""
    names = List[BuiltInCategory]()
    for name in categories:
        try:
            names.Add(getattr(BuiltInCategory, name))
        except AttributeError:
            pass
    outline = Outline(XYZ(*low), XYZ(*high))
    return (FilteredElementCollector(doc).WherePasses(ElementMulticategoryFilter(names))
            .WhereElementIsNotElementType().WherePasses(BoundingBoxIntersectsFilter(outline)))


def _box_in(transform, low, high):
    """The box low-high (feet) seen in a link: corners moved by the inverse."""
    inverse = transform.Inverse
    corners = [inverse.OfPoint(XYZ(x, y, z)) for x in (low[0], high[0])
               for y in (low[1], high[1]) for z in (low[2], high[2])]
    return ((min(p.X for p in corners), min(p.Y for p in corners), min(p.Z for p in corners)),
            (max(p.X for p in corners), max(p.Y for p in corners), max(p.Z for p in corners)))


def read_obstacles(doc, path, bounds, categories, links=True, skip=()):
    """Obstacles near a path of points (metres): within REACH beside it and
    between bounds (lowest, highest z in metres, None for 5 m off the path).
    skip: ids (ints) of host elements left out (the trays being rerouted)."""
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    zs = [p[2] for p in path]
    bottom = bounds[0] if bounds[0] is not None else min(zs) - 5.0
    top = bounds[1] if bounds[1] is not None else max(zs) + 5.0
    low = ((min(xs) - REACH) / M_PER_FOOT, (min(ys) - REACH) / M_PER_FOOT,
           (min(bottom, min(zs)) - 0.5) / M_PER_FOOT)
    high = ((max(xs) + REACH) / M_PER_FOOT, (max(ys) + REACH) / M_PER_FOOT,
            (max(top, max(zs)) + 0.5) / M_PER_FOOT)
    skip = set(skip)
    found = []
    for element in _collector(doc, categories, low, high):
        if id_int(element.Id) not in skip:
            found += _obstacles(element, element.Id, None, "")
    if not links:
        return found
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            continue
        transform = link.GetTotalTransform()
        link_low, link_high = _box_in(transform, low, high)
        suffix = u" (link %s)" % link_doc.Title
        for element in _collector(link_doc, categories, link_low, link_high):
            found += _obstacles(element, (link.Id, element.Id), transform, suffix)
    return found


# ---------------------------------------------------------------- existing trays

def is_tray(element):
    return isinstance(element, CableTray) and isinstance(
        getattr(element, "Location", None), LocationCurve)


def selected_trays(uidoc):
    doc = uidoc.Document
    elements = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    return [e for e in elements if e is not None and is_tray(e)]


def view_trays(doc, view):
    return [e for e in FilteredElementCollector(doc, view.Id).OfClass(CableTray) if is_tray(e)]


class _TrayFilter(ISelectionFilter):
    __namespace__ = "ElectricalCableTray"       # needed by the CPython engine

    def AllowElement(self, element):
        return is_tray(element)

    def AllowReference(self, reference, position):
        return False


def pick_trays(uidoc):
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _TrayFilter(), "Select the cable trays, then click Finish")
    except OperationCanceledException:
        return []
    doc = uidoc.Document
    return [doc.GetElement(r.ElementId) for r in refs]


def _connectors(element):
    try:
        return list(element.ConnectorManager.Connectors)
    except Exception:
        return []


def _end_connector(tray, point):
    """The tray's connector nearest a point (feet)."""
    found = _connectors(tray)
    return min(found, key=lambda c: c.Origin.DistanceTo(point)) if found else None


def _joined(connector, owner_id):
    """Connectors of other elements joined to this one."""
    found = []
    owner = id_int(owner_id)
    try:
        for other in connector.AllRefs:
            if other.Owner is not None and id_int(other.Owner.Id) != owner:
                found.append(other)
    except Exception:
        pass
    return found


def size(tray):
    """(width, height) in metres."""
    return tray.Width * M_PER_FOOT, tray.Height * M_PER_FOOT


def ends(tray):
    """(start, end, start joined, end joined): points in metres."""
    curve = tray.Location.Curve
    a, b = curve.GetEndPoint(0), curve.GetEndPoint(1)
    joined = []
    for point in (a, b):
        connector = _end_connector(tray, point)
        joined.append(bool(connector is not None and _joined(connector, tray.Id)))
    return _m(a), _m(b), joined[0], joined[1]


def neighbours(trays):
    """Ids (ints) of the trays and the fittings and trays joined to them."""
    found = set()
    for tray in trays:
        found.add(id_int(tray.Id))
        for connector in _connectors(tray):
            for other in _joined(connector, tray.Id):
                found.add(id_int(other.Owner.Id))
    return found


# ---------------------------------------------------------------- drawing

def _new_tray(doc, type_id, level_id, a, b, width, height, like=None):
    tray = CableTray.Create(doc, type_id, _xyz(a), _xyz(b), level_id)
    for bip, value in ((BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM, width),
                       (BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM, height)):
        parameter = tray.get_Parameter(bip)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(value / M_PER_FOOT)
    if like is not None:
        _copy_parameters(like, tray)
    return tray


def _copy_parameters(source, target):
    """Service type and comments, from the tray rerouted."""
    for name in ("RBS_CTC_SERVICE_TYPE", "ALL_MODEL_INSTANCE_COMMENTS"):
        try:
            bip = getattr(BuiltInParameter, name)
            value = source.get_Parameter(bip).AsString()
            parameter = target.get_Parameter(bip)
            if value and parameter is not None and not parameter.IsReadOnly:
                parameter.Set(value)
        except Exception:
            pass


def _elbows(doc, trays):
    """Elbows between consecutive trays. Returns the number that failed."""
    failed = 0
    for first, second in zip(trays, trays[1:]):
        point = first.Location.Curve.GetEndPoint(1)
        try:
            doc.Create.NewElbowFitting(_end_connector(first, point), _end_connector(second, point))
        except Exception:
            failed += 1
    return failed


def segments(points):
    """Consecutive points, with repeats dropped."""
    kept = [points[0]]
    for p in points[1:]:
        if sum((p[k] - kept[-1][k]) ** 2 for k in range(3)) > 1e-8:
            kept.append(p)
    return list(zip(kept, kept[1:]))


def draw(doc, points, type_id, level_id, width, height):
    """New trays along the points (metres), joined by elbows.
    Returns ([trays], elbows that failed)."""
    trays = [_new_tray(doc, type_id, level_id, a, b, width, height)
             for a, b in segments(points)]
    return trays, _elbows(doc, trays)


def reroute(doc, tray, points):
    """The tray rerouted along the points (metres), from its start to its
    end: it keeps its first piece, new trays of its type and size take
    the rest, and whatever its end was joined to is joined to the last.
    Returns ([trays], elbows or joins that failed)."""
    curve = tray.Location.Curve
    end = curve.GetEndPoint(1)
    end_connector = _end_connector(tray, end)
    joined = _joined(end_connector, tray.Id) if end_connector is not None else []
    for other in joined:
        end_connector.DisconnectFrom(other)
    width, height = size(tray)
    pieces = segments(points)
    a, b = pieces[0]
    tray.Location.Curve = Line.CreateBound(_xyz(a), _xyz(b))
    trays = [tray] + [_new_tray(doc, tray.GetTypeId(), tray.ReferenceLevel.Id, p, q,
                                width, height, like=tray) for p, q in pieces[1:]]
    failed = _elbows(doc, trays)
    last = _end_connector(trays[-1], end)
    for other in joined:
        try:
            last.ConnectTo(other)
        except Exception:
            failed += 1
    return trays, failed


def select(uidoc, element_ids):
    uidoc.Selection.SetElementIds(List[ElementId](element_ids))
