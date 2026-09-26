# -*- coding: utf-8 -*-
"""Revit side: devices in the active plan -> dimension strings.

Devices are family instances in this model. Each is dimensioned to the
centre reference planes of its family, Center (Left/Right) and Center
(Front/Back), those that stand upright in the plan. A family whose centre
plane is set as a Strong or Weak reference is found by the plane's name.

Walls (and curtain panels and mullions) are found with rays shot from the
devices along the strings, 150 mm below each device (under the ceiling
for ceiling devices, above the doors), through this model and linked
models, in a temporary 3D view deleted again at the end. A face in a link
is dimensioned through a link reference; when Revit does not take it the
string is made without it.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Dimension, DimensionStyleType, DimensionType,
    ElementId, ElementMulticategoryFilter, ElementTypeGroup, FamilyInstance,
    FamilyInstanceReferenceType, FilteredElementCollector, FindReferenceTarget, Line,
    ReferenceArray, ReferenceIntersector, Transaction, TransactionGroup, TransactionStatus,
    View3D, ViewFamily, ViewFamilyType, ViewPlan, XYZ,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

from dims.chains import ANGLE_TOL, Device, Hit, plan
from dims.report import Run
from firealarm.layout import point_in_loops
from firealarm.revit_fa import boundary_loops, selected_spaces, type_label

M_PER_FOOT = 0.3048
RAY_DROP = 0.5          # ft (150 mm): walls are looked for this far below each device
RAY_MIN = 1.0           # ft: and at least this far above the view's level
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


def _centre(instance, ref_type, name):
    """Reference to a centre plane of the instance's family, or None."""
    try:
        refs = list(instance.GetReferences(ref_type))
    except Exception:
        refs = []
    if refs:
        return refs[0]
    for other in (FamilyInstanceReferenceType.StrongReference,
                  FamilyInstanceReferenceType.WeakReference):
        try:
            for ref in instance.GetReferences(other):
                if instance.GetReferenceName(ref) == name:
                    return ref
        except Exception:
            pass
    return None


def read_devices(instances):
    """([Device], {(family : type, note): count}) of the family instances.
    Devices without a centre plane upright in the plan are left out."""
    devices, notes = [], {}
    for instance in instances:
        point = _point(instance)
        transform = instance.GetTransform()
        axes, missing = [], []
        for ref_type, basis, name in CENTRES:
            axis = getattr(transform, basis)
            if abs(axis.Z) > UPRIGHT:
                continue                    # the plane lies flat in the plan
            ref = _centre(instance, ref_type, name)
            if ref is None:
                missing.append(name)
            else:
                axes.append((math.atan2(axis.Y, axis.X), ref))
        label = type_label(instance.Symbol)
        note = None
        if missing:
            note = "no %s reference plane in the family, %s" % (
                " or ".join(missing), "dimensioned one way only" if axes else "not dimensioned")
        elif not axes:
            note = "tilted, not square to the plan: not dimensioned"
        if note:
            notes[(label, note)] = notes.get((label, note), 0) + 1
        if axes:
            devices.append(Device(instance.Id, point.X * M_PER_FOOT, point.Y * M_PER_FOOT, axes,
                                  z=point.Z * M_PER_FOOT, label=label))
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


class _Face(object):
    """A face found by a ray: its normal in this model (None when not
    known), whether it is flat, whether it is in a link, and the
    references to dimension to, the one to try first first."""

    def __init__(self, doc, reference):
        self.normal, self.flat = None, True
        self.refs = [reference]
        self.linked = _is_linked(reference)
        link = doc.GetElement(reference.ElementId) if self.linked else None
        try:
            if link is not None:
                inner = reference.CreateReferenceInLink()
                element = link.GetLinkDocument().GetElement(inner.ElementId)
                face = element.GetGeometryObjectFromReference(inner)
            else:
                face = doc.GetElement(reference.ElementId).GetGeometryObjectFromReference(reference)
        except Exception:
            face = None
        if face is not None:
            normal = getattr(face, "FaceNormal", None)
            if normal is not None:
                self.normal = link.GetTotalTransform().OfVector(normal) if link is not None \
                    else normal
            elif face.GetType().Name != "PlanarFace":
                self.flat = False               # curved: cannot be dimensioned
        if link is not None:
            try:
                self.refs.insert(0, reference.CreateReferenceInLink().CreateLinkReference(link))
            except Exception:
                pass


class WallFinder(object):
    """find_wall() for chains.plan(): the first wall face from a device
    along a direction, in this model or a linked model."""

    def __init__(self, doc, view3d, level_z=None):
        self.doc = doc
        self.level_z = level_z              # ft, the plan's level
        categories = List[BuiltInCategory]()
        for bic in WALL_CATEGORIES:
            categories.Add(bic)
        self.intersector = ReferenceIntersector(
            ElementMulticategoryFilter(categories), FindReferenceTarget.Face, view3d)
        self.intersector.FindReferencesInRevitLinks = True

    def __call__(self, device, direction):
        z = device.z / M_PER_FOOT - RAY_DROP
        if self.level_z is not None:
            z = max(z, self.level_z + RAY_MIN)
        origin = XYZ(device.x / M_PER_FOOT, device.y / M_PER_FOOT, z)
        ray = XYZ(direction[0], direction[1], 0)
        found = sorted(self.intersector.Find(origin, ray), key=lambda f: f.Proximity)
        for hit in found:
            if hit.Proximity < 0:
                continue
            face = _Face(self.doc, hit.GetReference())
            if face.normal is not None and face.normal.DotProduct(ray) > UPRIGHT:
                continue                        # leaving a face: the wall behind the device
            square = face.flat and (face.normal is None or
                                    abs(face.normal.DotProduct(ray)) >= math.cos(ANGLE_TOL))
            return Hit(hit.Proximity * M_PER_FOOT, face, square)
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
              to_walls=True, old=()):
    """Plan the strings of `devices` ([Device]) and make them in `view`,
    one undo. `old`: dimensions deleted when new ones are made. Returns a
    report.Run; nothing is changed when no string is made."""
    run = Run(view.Name, len(devices))
    level = getattr(view, "GenLevel", None)
    level_z = level.ProjectElevation if level is not None else None
    z = level_z if level_z is not None else 0.0
    offset = offset_mm / 1000.0 * view.Scale            # m in the model
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
                       to_walls=to_walls, right=(right.X, right.Y), up=(up.X, up.Y))
        run.alone = len(set(id(d) for d, _ in planned.alone))
        run.no_wall, run.skew = planned.no_wall, planned.skew

        t = Transaction(doc, "Dimension Devices")
        t.Start()
        for chain in planned.chains:
            (x0, y0), (x1, y1) = chain.line(offset)
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
