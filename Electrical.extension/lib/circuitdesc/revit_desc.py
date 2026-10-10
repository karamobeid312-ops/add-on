# -*- coding: utf-8 -*-
"""Boards and their circuits read from Revit, the room or space each
fixture is in (in the architectural link, else in this model), and the
descriptions written to the circuits' Load Name."""
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, FilteredElementCollector, LocationCurve,
    LocationPoint, RevitLinkInstance, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from circuitdesc.describe import Circuit, label

FEET = 0.3048                   # metres in a foot
SIDE_STEP = 0.3 / FEET          # off the wall, for fixtures on a wall face
# heights tried above / below the fixture: ceiling lights sit above the
# room's upper limit, floor boxes just under its base
HEIGHT_STEPS = [h / FEET for h in (0.0, 0.3, -0.5, -1.0, -1.5, -2.0, -2.5)]
ABOVE_LEVEL = 0.1 / FEET        # never look below its level


def id_int(element_id):
    try:
        return element_id.Value            # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _bip_text(element, name):
    try:
        p = element.get_Parameter(getattr(BuiltInParameter, name))
        return (p.AsString() or p.AsValueString() or u"") if p is not None else u""
    except Exception:
        return u""


def panel_name(element):
    return (_bip_text(element, "RBS_ELEC_PANEL_NAME") or element.Name or u"").strip()


def _circuit_kind(system):
    try:
        from Autodesk.Revit.DB.Electrical import CircuitType
        return system.CircuitType != CircuitType.Circuit
    except Exception:
        return False


def _is_board(element):
    try:
        return id_int(element.Category.Id) == int(BuiltInCategory.OST_ElectricalEquipment)
    except Exception:
        return False


# ---------------------------------------------------------------- boards

def power_circuits(doc):
    """{board id: [circuits]} for the power circuits of every board,
    spares and spaces left out."""
    out = {}
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        try:
            if system.SystemType != ElectricalSystemType.PowerCircuit:
                continue
            if system.BaseEquipment is None or _circuit_kind(system):
                continue
            out.setdefault(id_int(system.BaseEquipment.Id), []).append(system)
        except Exception:
            continue
    return out


def boards(doc, circuits):
    """[(name, element)] of the boards with circuits, by name."""
    found = []
    for board_id in circuits:
        element = doc.GetElement(ElementId(board_id))
        if element is not None:
            found.append((panel_name(element), element))
    return sorted(found, key=lambda b: b[0])


def chosen_boards(doc, uidoc):
    """Boards picked before clicking: the board of the open panel
    schedule, or selected boards."""
    try:
        from Autodesk.Revit.DB.Electrical import PanelScheduleView
        view = doc.ActiveView
        if isinstance(view, PanelScheduleView):
            board = doc.GetElement(view.GetPanel())
            if board is not None:
                return [board]
    except Exception:
        pass
    picked = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    return [e for e in picked if e is not None and _is_board(e)]


# ---------------------------------------------------------------- rooms

class Model(object):
    """A model whose rooms and spaces are looked up: a link, or this one."""

    def __init__(self, doc, link=None):
        self.doc = doc
        self.to_model = link.GetTotalTransform().Inverse if link is not None else None
        self.spaces = link is None          # Spaces only in this model

    def find(self, point):
        p = self.to_model.OfPoint(point) if self.to_model is not None else point
        if self.spaces:
            try:
                space = self.doc.GetSpaceAtPoint(p)
                if space is not None:
                    return space
            except Exception:
                pass
        try:
            return self.doc.GetRoomAtPoint(p)
        except Exception:
            return None


def linked_models(doc):
    """The loaded links (the architectural model among them)."""
    found = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is not None:
            found.append(Model(link_doc, link))
    return found


def _location(element):
    loc = element.Location
    if isinstance(loc, LocationPoint):
        return loc.Point
    if isinstance(loc, LocationCurve):
        return loc.Curve.Evaluate(0.5, True)
    box = element.get_BoundingBox(None)
    if box is not None:
        return box.Min.Add(box.Max).Multiply(0.5)
    return None


def _floor(element):
    """Elevation of the fixture's level, or None."""
    doc = element.Document
    for level_id in (getattr(element, "LevelId", None),):
        if level_id is not None and id_int(level_id) > 0:
            level = doc.GetElement(level_id)
            if level is not None:
                return level.Elevation
    for name in ("FAMILY_LEVEL_PARAM", "INSTANCE_REFERENCE_LEVEL_PARAM",
                 "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM"):
        try:
            p = element.get_Parameter(getattr(BuiltInParameter, name))
            level = doc.GetElement(p.AsElementId()) if p is not None else None
            if level is not None:
                return level.Elevation
        except Exception:
            pass
    return None


def _candidates(element):
    """Points to look for the fixture's room at: where it is, a little off
    its wall, then lower or higher."""
    point = _location(element)
    if point is None:
        return []
    sides = [XYZ.Zero]
    try:
        facing = element.FacingOrientation
        flat = XYZ(facing.X, facing.Y, 0)
        if flat.GetLength() > 0.5:
            flat = flat.Normalize().Multiply(SIDE_STEP)
            sides += [flat, flat.Negate()]
    except Exception:
        pass
    floor = _floor(element)
    out = []
    for dz in HEIGHT_STEPS:
        z = point.Z + dz
        if dz < 0 and floor is not None and z < floor + ABOVE_LEVEL:
            continue
        for side in sides:
            out.append(XYZ(point.X + side.X, point.Y + side.Y, z))
    return out


def find_space(element, models):
    """The room or space the fixture is in, from the first model that has one."""
    points = _candidates(element)
    for model in models:
        for p in points:
            found = model.find(p)
            if found is not None:
                return found
    return None


def space_label(space, style, upper):
    return label(_bip_text(space, "ROOM_NUMBER"), _bip_text(space, "ROOM_NAME"), style, upper)


# ---------------------------------------------------------------- circuits

def _slot(system):
    try:
        return system.StartSlot
    except Exception:
        return None


def read(board, systems, models, values):
    """[Circuit] of one board, with the room of every fixture."""
    name = panel_name(board)
    cache = {}
    out = []
    for system in systems:
        elements = [e for e in system.Elements if e is not None]
        feeder = any(_is_board(e) and id_int(e.Id) != id_int(board.Id) for e in elements)
        labels = []
        if not feeder:
            for element in elements:
                key = id_int(element.Id)
                if key not in cache:
                    space = find_space(element, models)
                    cache[key] = (space_label(space, values["style"], values["upper"])
                                  if space is not None else None)
                labels.append(cache[key])
        out.append(Circuit(system, name, system.CircuitNumber or u"", _slot(system),
                           system.LoadName, labels, feeder))
    return out


def write(circuits):
    """Write the new descriptions; [(circuit, error)] of those that failed."""
    failed = []
    for circuit in circuits:
        try:
            circuit.ref.LoadName = circuit.new
        except Exception:
            try:
                p = circuit.ref.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NAME)
                if p is None or p.IsReadOnly or not p.Set(circuit.new):
                    raise Exception("Load Name is read only")
            except Exception as error:
                failed.append((circuit, error))
    return failed
