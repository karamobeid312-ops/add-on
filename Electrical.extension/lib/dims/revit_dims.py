# -*- coding: utf-8 -*-
"""Revit side: devices in the active plan -> dimension strings.

Devices are family instances in this model. Each is dimensioned to the
centre reference planes of its family, Center (Left/Right) and Center
(Front/Back), those that stand upright in the plan. A centre plane set as
a Strong or Weak reference is found by its name, or else by its position:
the plane through the insertion point.

A device on a wall (face based on an upright face, or hosted by a wall) is
dimensioned along its wall only, and its rays start 150 mm into the room.

Walls (and curtain panels and mullions) are found with rays shot from the
devices along the strings: 150 mm below each device (under the ceiling
for ceiling devices, above the doors) and 0.5 m above the plan's level
(under the windows). A door or window a ray meets stands for the wall it
is in. The rays go through this model and linked models, in a temporary
3D view deleted again at the end. A face in a link is dimensioned through
a link reference; when Revit does not take it the string is made without
it.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Dimension, DimensionStyleType, DimensionType,
    ElementId, ElementMulticategoryFilter, ElementTypeGroup, FamilyInstance,
    FamilyInstanceReferenceType, FilteredElementCollector, FindReferenceTarget,
    HostObjectUtils, Line, ReferenceArray, ReferenceIntersector, ShellLayerType, SketchPlane,
    Transaction, TransactionGroup, TransactionStatus, View3D, ViewFamily, ViewFamilyType, ViewPlan,
    XYZ,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from dims.chains import ANGLE_TOL, NEAREST, Device, Hit, plan
from dims.report import Run
from firealarm.layout import point_in_loops
from firealarm.revit_fa import boundary_loops, selected_spaces, type_label

M_PER_FOOT = 0.3048
RAY_DROP = 0.5          # ft (150 mm): walls are looked for this far below each device
RAY_MIN = 1.0           # ft: and at least this far above the view's level
RAY_LOW = 1.6           # ft (0.5 m): and again this far above the view's level
RAY_GAP = 1.0           # ft: when that is at least this far below the first ray
WALL_TALL = 6.5         # ft (2 m): a wall only the lower ray meets counts from this tall
WALL_OFF = 0.5          # ft (150 mm): rays of a device on a wall start this far into the room
TEXT_ROOM = 4.0         # mm on paper: more space when the text of a string along a wall
                        # would face the wall, so it clears the device symbols
PLANE_TOL = 0.01        # ft (3 mm): a reference plane this near the insertion point is a centre
UPRIGHT = 1e-3          # a centre plane whose normal rises more than this is flat in the plan
SPACE_HEIGHT = 15.0     # ft: devices this high above a space's floor are in it (rooms
                        # are often modelled lower than the ceiling)

# Categories taken for "All devices in this view" and devices in spaces.
DEVICE_CATEGORIES = (
    BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_LightingDevices, BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_SecurityDevices, BuiltInCategory.OST_NurseCallDevices,
    BuiltInCategory.OST_TelephoneDevices, BuiltInCategory.OST_GenericModel,
)

WALL_CATEGORIES = (
    BuiltInCategory.OST_Walls, BuiltInCategory.OST_CurtainWallPanels,
    BuiltInCategory.OST_CurtainWallMullions,
)
# a door or window a ray meets stands for the wall it is in
OPENING_CATEGORIES = (BuiltInCategory.OST_Doors, BuiltInCategory.OST_Windows)
_OPENINGS = set(int(bic) for bic in OPENING_CATEGORIES)
_WALL = int(BuiltInCategory.OST_Walls)

# centre planes: reference type, the instance axis that is the plane's normal, its name
CENTRES = (
    (FamilyInstanceReferenceType.CenterLeftRight, "BasisX", "Center (Left/Right)"),
    (FamilyInstanceReferenceType.CenterFrontBack, "BasisY", "Center (Front/Back)"),
)


# ---------------------------------------------------------------- helpers

def id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _point(element):
    return getattr(getattr(element, "Location", None), "Point", None)


def _is_linked(reference):
    return id_int(reference.LinkedElementId) != id_int(ElementId.InvalidElementId)


def is_plan(view):
    """Floor, ceiling, structural or area plan (not a template)."""
    return isinstance(view, ViewPlan) and not view.IsTemplate


def is_device(element):
    """A family instance placed at a point."""
    return isinstance(element, FamilyInstance) and _point(element) is not None


def _type_name(element_type):
    for bip in (BuiltInParameter.SYMBOL_NAME_PARAM, BuiltInParameter.ALL_MODEL_TYPE_NAME):
        try:
            p = element_type.get_Parameter(bip)
            if p is not None and p.AsString():
                return p.AsString()
        except Exception:
            pass
    try:
        return element_type.Name
    except Exception:
        return ""


# ---------------------------------------------------------------- devices

def visible_ids(doc, view):
    """Ids (int) of the family instances shown in the view."""
    return set(id_int(i) for i in
               FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance).ToElementIds())


def view_devices(doc, view):
    """Devices of DEVICE_CATEGORIES shown in the view, not the parts
    nested in another family."""
    found = []
    for bic in DEVICE_CATEGORIES:
        for element in FilteredElementCollector(doc, view.Id).OfCategory(bic) \
                .OfClass(FamilyInstance):
            if element.SuperComponent is None and _point(element) is not None:
                found.append(element)
    return found


def by_category(instances):
    """[(category name, [instances])], the biggest first."""
    groups = {}
    for instance in instances:
        name = instance.Category.Name if instance.Category is not None else "Other"
        groups.setdefault(name, []).append(instance)
    return sorted(groups.items(), key=lambda g: (-len(g[1]), g[0]))


def selection(uidoc):
    """(devices, spaces) selected before clicking: family instances at a
    point, and spaces or rooms (SpaceRef) of this model or of links."""
    doc = uidoc.Document
    elements = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    return [e for e in elements if e is not None and is_device(e)], selected_spaces(uidoc)


class _DeviceFilter(ISelectionFilter):
    __namespace__ = "ElectricalDimensions"      # needed by the CPython engine

    def AllowElement(self, element):
        return is_device(element)

    def AllowReference(self, reference, position):
        return False


def pick_devices(uidoc):
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _DeviceFilter(), "Select the devices, then click Finish")
    except OperationCanceledException:
        return []
    doc = uidoc.Document
    return [doc.GetElement(r.ElementId) for r in refs]


def in_spaces(instances, spaces):
    """The instances inside the spaces or rooms ([SpaceRef])."""
    outlines = []
    for ref in spaces:
        loops = boundary_loops(ref)
        if not loops:
            continue
        box = ref.space.get_BoundingBox(None)
        heights = (ref.point(box.Min).Z, ref.point(box.Max).Z) if box is not None else None
        outlines.append((loops, heights))
    found = []
    for instance in instances:
        p = _point(instance)
        for loops, heights in outlines:
            if heights is not None:
                bottom, top = heights
                if not bottom - 1.0 <= p.Z <= max(top, bottom + SPACE_HEIGHT) + 1.0:
                    continue
            if point_in_loops(p.X * M_PER_FOOT, p.Y * M_PER_FOOT, loops):
                found.append(instance)
                break
    return found


_STRONG_WEAK = (FamilyInstanceReferenceType.StrongReference,
                FamilyInstanceReferenceType.WeakReference)


class _CentreFinder(object):
    """Centre planes of families that do not mark them as Center (Left/
    Right) or Center (Front/Back): the Strong or Weak reference plane square
    to the axis through the insertion point. Found once per family type, by
    making a sketch plane on each reference (rolled back)."""

    def __init__(self, doc):
        self.doc = doc
        self.found = {}             # (type id, basis) -> (reference type, index, name) or None

    def centre(self, instance, basis):
        try:
            key = (id_int(instance.GetTypeId()), basis)
        except Exception:
            return None
        if key not in self.found:
            self.found[key] = self._probe(instance, basis)
        if self.found[key] is None:
            return None
        ref_type, index, name = self.found[key]
        try:
            refs = list(instance.GetReferences(ref_type))
            if index < len(refs) and (instance.GetReferenceName(refs[index]) or "") == name:
                return refs[index]
            for ref in refs:                # listed in another order: by its name
                if name and instance.GetReferenceName(ref) == name:
                    return ref
        except Exception:
            pass
        return None

    def _probe(self, instance, basis):
        transform = instance.GetTransform()
        axis, origin = getattr(transform, basis), transform.Origin
        t = Transaction(self.doc, "Find centre planes")
        try:
            t.Start()
            for ref_type in _STRONG_WEAK:
                for index, ref in enumerate(instance.GetReferences(ref_type)):
                    try:
                        plane = SketchPlane.Create(self.doc, ref).GetPlane()
                    except Exception:
                        continue
                    normal = plane.Normal
                    if abs(normal.DotProduct(axis)) >= math.cos(ANGLE_TOL) and \
                            abs(plane.Origin.Subtract(origin).DotProduct(normal)) <= PLANE_TOL:
                        return ref_type, index, instance.GetReferenceName(ref) or ""
        except Exception:
            pass
        finally:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
        return None


def _centre(instance, ref_type, name, basis, finder=None):
    """Reference to a centre plane of the instance's family, or None: the
    plane set as `ref_type`, a Strong or Weak one named `name`, or one found
    by its position."""
    try:
        refs = list(instance.GetReferences(ref_type))
    except Exception:
        refs = []
    if refs:
        return refs[0]
    for other in _STRONG_WEAK:
        try:
            for ref in instance.GetReferences(other):
                if instance.GetReferenceName(ref) == name:
                    return ref
        except Exception:
            pass
    return finder.centre(instance, basis) if finder is not None else None


_KINDS = ("Left", "CenterLeftRight", "Right", "Front", "CenterFrontBack", "Back", "Bottom",
          "CenterElevation", "Top", "StrongReference", "WeakReference")


def _reference_names(instance):
    """Names of the references the instance's family has (for the summary)."""
    names = []
    for kind in _KINDS:
        try:
            for ref in instance.GetReferences(getattr(FamilyInstanceReferenceType, kind)):
                name = instance.GetReferenceName(ref) or kind
                if name not in names:
                    names.append(name)
        except Exception:
            pass
    return names


def _unit(x, y):
    length = math.hypot(x, y)
    return (x / length, y / length) if length > 1e-6 else None


def _facing(instance, transform):
    """(x, y) out of the wall into the room, for a device on a wall: face
    based on an upright face, or hosted by a wall. None otherwise."""
    z = transform.BasisZ
    if abs(z.Z) <= UPRIGHT:
        return _unit(z.X, z.Y)              # face based: its Z is the face's normal
    try:
        host = instance.Host
        if host is None or id_int(host.Category.Id) != _WALL:
            return None
        point = _point(instance)
        on = host.Location.Curve.Project(point).XYZPoint
        found = _unit(point.X - on.X, point.Y - on.Y)
        if found is None:
            facing = instance.FacingOrientation
            found = _unit(facing.X, facing.Y)
        return found
    except Exception:
        return None


def read_devices(instances):
    """([Device], {(family : type, note): count}) of the family instances.
    Devices without a centre plane upright in the plan are left out."""
    devices, notes = [], {}
    doc = getattr(instances[0], "Document", None) if instances else None
    finder = _CentreFinder(doc) if doc is not None else None
    for instance in instances:
        point = _point(instance)
        transform = instance.GetTransform()
        facing = _facing(instance, transform)
        axes, missing = [], []
        for ref_type, basis, name in CENTRES:
            axis = getattr(transform, basis)
            if abs(axis.Z) > UPRIGHT:
                continue                    # the plane lies flat in the plan
            if facing is not None and abs(axis.X * facing[0] + axis.Y * facing[1]) > UPRIGHT:
                continue                    # across its wall: a device on a wall goes along it
            ref = _centre(instance, ref_type, name, basis, finder)
            if ref is None:
                missing.append(name)
            else:
                axes.append((math.atan2(axis.Y, axis.X), ref))
        label = type_label(instance.Symbol)
        note = None
        if missing:
            names = _reference_names(instance)
            note = "no %s reference plane in the family, %s (%s)" % (
                " or ".join(missing), "dimensioned one way only" if axes else "not dimensioned",
                "its references: " + ", ".join(names) if names else "it has no references")
        elif not axes:
            note = "tilted, not square to the plan: not dimensioned"
        if note:
            notes[(label, note)] = notes.get((label, note), 0) + 1
        if axes:
            devices.append(Device(instance.Id, point.X * M_PER_FOOT, point.Y * M_PER_FOOT, axes,
                                  z=point.Z * M_PER_FOOT, label=label, facing=facing))
    return devices, notes


# ---------------------------------------------------------------- walls

def _ray_view(doc, plan_view):
    """A plain 3D view for the rays: no template or section box, walls and
    links shown, the plan's phase. Deleted again at the end."""
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
    for bic in WALL_CATEGORIES + (BuiltInCategory.OST_RvtLinks,):
        try:
            view.SetCategoryHidden(ElementId(bic), False)
        except Exception:
            pass
    try:
        phase = plan_view.get_Parameter(BuiltInParameter.VIEW_PHASE).AsElementId()
        view.get_Parameter(BuiltInParameter.VIEW_PHASE).Set(phase)
    except Exception:
        pass
    return view


def _top(element, transform):
    """Top of the element in this model (ft), or None."""
    try:
        top = element.get_BoundingBox(None).Max
        return transform.OfPoint(top).Z if transform is not None else top.Z
    except Exception:
        return None


def _opening_wall(element):
    """The wall a door or window is in, or None."""
    try:
        if id_int(element.Category.Id) not in _OPENINGS:
            return None
        host = element.Host
        return host if id_int(host.Category.Id) == _WALL else None
    except Exception:
        return None


def _side_face(wall, transform, origin, ray):
    """(distance ft, normal, reference) of the side face of `wall` that
    faces the ray from `origin`, the nearest one ahead, or None."""
    best = None
    for side in (ShellLayerType.Exterior, ShellLayerType.Interior):
        try:
            refs = list(HostObjectUtils.GetSideFaces(wall, side))
        except Exception:
            continue
        for ref in refs:
            try:
                face = wall.GetGeometryObjectFromReference(ref)
                normal, point = face.FaceNormal, face.Origin
            except Exception:
                continue
            if transform is not None:
                normal, point = transform.OfVector(normal), transform.OfPoint(point)
            facing = normal.DotProduct(ray)
            if facing > -UPRIGHT:
                continue                        # not facing the ray
            distance = point.Subtract(origin).DotProduct(normal) / facing
            if distance >= 0 and (best is None or distance < best[0]):
                best = (distance, normal, ref)
    return best


class _Face(object):
    """The wall face a ray meets: its distance (ft), its normal in this
    model (None when not known), whether it is flat, whether it is in a
    link, the references to dimension to (the one to try first first) and
    the top of its wall (ft, None when not known). A door or window stands
    for the side face of the wall it is in. skip: not a face to stop at."""

    def __init__(self, doc, reference, proximity, origin, ray):
        self.distance, self.normal, self.flat = proximity, None, True
        self.top, self.skip = None, False
        self.refs = [reference]
        self.linked = _is_linked(reference)
        link = doc.GetElement(reference.ElementId) if self.linked else None
        transform = link.GetTotalTransform() if link is not None else None
        try:
            inner = reference.CreateReferenceInLink() if link is not None else reference
            source = link.GetLinkDocument() if link is not None else doc
            element = source.GetElement(inner.ElementId)
        except Exception:
            return
        wall = _opening_wall(element)
        if wall is not None:
            found = _side_face(wall, transform, origin, ray)
            try:
                self.distance, self.normal, ref = found
                self.refs = [ref.CreateLinkReference(link) if link is not None else ref]
            except Exception:
                self.skip = True                # the wall's faces cannot be read
                return
            self.top = _top(wall, transform)
            return
        try:
            face = element.GetGeometryObjectFromReference(inner)
        except Exception:
            face = None
        if face is not None:
            normal = getattr(face, "FaceNormal", None)
            if normal is not None:
                self.normal = transform.OfVector(normal) if transform is not None else normal
            elif face.GetType().Name != "PlanarFace":
                self.flat = False               # curved: cannot be dimensioned
        if link is not None:
            try:
                self.refs.insert(0, inner.CreateLinkReference(link))
            except Exception:
                pass
        self.top = _top(element, transform)


class WallFinder(object):
    """find_wall() for chains.plan(): the first wall face from a device
    along a direction, in this model or a linked model.

    Two rays: RAY_DROP below the device (above the doors, for ceiling
    devices), and RAY_LOW above the plan's level (under the windows, and
    for walls that stop short of the device). A door or window a ray meets
    stands for the wall it is in. The nearer wall wins, but the lower ray
    only counts walls at least WALL_TALL high, not half walls."""

    def __init__(self, doc, view3d, level_z=None):
        self.doc = doc
        self.level_z = level_z              # ft, the plan's level
        categories = List[BuiltInCategory]()
        for bic in WALL_CATEGORIES + OPENING_CATEGORIES:
            categories.Add(bic)
        self.intersector = ReferenceIntersector(
            ElementMulticategoryFilter(categories), FindReferenceTarget.Face, view3d)
        self.intersector.FindReferencesInRevitLinks = True

    def __call__(self, device, direction):
        x, y = device.x / M_PER_FOOT, device.y / M_PER_FOOT
        if device.facing is not None:       # on a wall: from off the wall, in the room
            x, y = x + device.facing[0] * WALL_OFF, y + device.facing[1] * WALL_OFF
        ray = XYZ(direction[0], direction[1], 0)
        high = device.z / M_PER_FOOT - RAY_DROP
        if self.level_z is not None:
            high = max(high, self.level_z + RAY_MIN)
        face = self._first(XYZ(x, y, high), ray)
        if self.level_z is not None and high - (self.level_z + RAY_LOW) >= RAY_GAP:
            low = self._first(XYZ(x, y, self.level_z + RAY_LOW), ray, self.level_z + WALL_TALL)
            if low is not None and (face is None or low.distance < face.distance - 1e-6):
                face = low
        if face is None:
            return None
        square = face.flat and (face.normal is None or
                                abs(face.normal.DotProduct(ray)) >= math.cos(ANGLE_TOL))
        return Hit(face.distance * M_PER_FOOT, face, square)

    def _first(self, origin, ray, min_top=None):
        """The first face the ray from `origin` stops at, or None. With
        min_top, walls whose top is lower (half walls) are passed."""
        for hit in sorted(self.intersector.Find(origin, ray), key=lambda f: f.Proximity):
            if hit.Proximity < 0:
                continue
            face = _Face(self.doc, hit.GetReference(), hit.Proximity, origin, ray)
            if face.skip or (face.normal is not None and face.normal.DotProduct(ray) > UPRIGHT):
                continue                        # leaving a face: the wall behind the device
            if min_top is not None and face.top is not None and face.top < min_top:
                continue
            return face
        return None


# ---------------------------------------------------------------- dimensions

def dimension_types(doc):
    """{name: DimensionType}: the linear dimension types of the model."""
    found = {}
    for dim_type in FilteredElementCollector(doc).OfClass(DimensionType):
        try:
            if dim_type.StyleType != DimensionStyleType.Linear:
                continue
        except Exception:
            continue
        name = _type_name(dim_type)
        if name and name not in found:
            found[name] = dim_type
    return found


def default_type_name(doc):
    try:
        dim_type = doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.LinearDimensionType))
        return _type_name(dim_type) if dim_type is not None else ""
    except Exception:
        return ""


def dimensions_hidden(view):
    try:
        return view.GetCategoryHidden(ElementId(BuiltInCategory.OST_Dimensions))
    except Exception:
        return False


def dimensions_to(doc, view, device_ids):
    """Ids of the dimensions in the view that go to any of the devices."""
    wanted = set(id_int(i) for i in device_ids)
    found = []
    for dim in FilteredElementCollector(doc, view.Id).OfClass(Dimension):
        try:
            if any(id_int(r.ElementId) in wanted for r in dim.References):
                found.append(dim.Id)
        except Exception:
            pass
    return found


def _make(doc, view, chain, line, dim_type):
    """(Dimension or None, walls left out, error). Tries the walls with
    their first reference; walls in links with their other reference;
    without the walls in links; then between the devices only."""
    walls = [s.ref for s in chain.stops if s.is_wall]      # _Face
    linked = [w for w in walls if w.linked]
    tries = []
    if walls:
        tries.append(lambda w: w.refs[0])
        if any(len(w.refs) > 1 for w in linked):
            tries.append(lambda w: w.refs[-1])
        if linked and len(linked) < len(walls):
            tries.append(lambda w: None if w.linked else w.refs[0])
    tries.append(lambda w: None)
    error = None
    for pick in tries:
        refs, dropped = ReferenceArray(), 0
        for stop in chain.stops:
            ref = pick(stop.ref) if stop.is_wall else stop.ref
            if ref is None:
                dropped += 1
            else:
                refs.Append(ref)
        if refs.Size < 2:
            continue
        try:
            if dim_type is not None:
                dim = doc.Create.NewDimension(view, line, refs, dim_type)
            else:
                dim = doc.Create.NewDimension(view, line, refs)
        except Exception as err:
            error = err
            continue
        if dim is not None:
            return dim, dropped, None
    return None, 0, error or "Revit did not take the references"


def dimension(doc, view, devices, dim_type=None, offset_mm=5.0, every_row=True,
              walls=NEAREST, old=()):
    """Plan the strings of `devices` ([Device]) and make them in `view`,
    one undo. walls: chains.NEAREST, BOTH or NONE. `old`: dimensions
    deleted when new ones are made. Returns a report.Run; nothing is
    changed when no string is made."""
    run = Run(view.Name, len(devices))
    level = getattr(view, "GenLevel", None)
    level_z = level.ProjectElevation if level is not None else None
    z = level_z if level_z is not None else 0.0
    offset = offset_mm / 1000.0 * view.Scale            # m in the model
    extra = TEXT_ROOM / 1000.0 * view.Scale
    right, up = view.RightDirection, view.UpDirection
    group = TransactionGroup(doc, "Dimension Devices")
    group.Start()
    t = None
    try:
        t = Transaction(doc, "Dimension view")
        t.Start()
        ray_view = _ray_view(doc, view)
        t.Commit()

        planned = plan(devices, WallFinder(doc, ray_view, level_z), every_row=every_row,
                       walls=walls, right=(right.X, right.Y), up=(up.X, up.Y))
        run.alone = len(set(id(d) for d, _ in planned.alone))
        run.no_wall, run.skew = planned.no_wall, planned.skew
        run.other_no_wall, run.other_skew = planned.other_no_wall, planned.other_skew

        t = Transaction(doc, "Dimension Devices")
        t.Start()
        for chain in planned.chains:
            (x0, y0), (x1, y1) = chain.line(offset, extra)
            line = Line.CreateBound(XYZ(x0 / M_PER_FOOT, y0 / M_PER_FOOT, z),
                                    XYZ(x1 / M_PER_FOOT, y1 / M_PER_FOOT, z))
            dim, dropped, error = _make(doc, view, chain, line, dim_type)
            if dim is None:
                run.failed.append(u"%s" % error)
                continue
            run.made.append(dim.Id)
            if dropped:
                run.no_walls += 1
        if run.made and old:
            doc.Delete(List[ElementId](list(old)))
            run.replaced = len(old)
        doc.Delete(ray_view.Id)
        if t.Commit() != TransactionStatus.Committed:
            run.failed.extend(["Revit did not accept them"] * len(run.made))
            run.made, run.no_walls, run.replaced = [], 0, 0
        if run.made:
            group.Assimilate()
        else:
            group.RollBack()
    except Exception:
        if t is not None and t.HasStarted() and not t.HasEnded():
            t.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
    return run
