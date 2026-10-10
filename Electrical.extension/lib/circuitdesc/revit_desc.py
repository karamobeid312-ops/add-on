# -*- coding: utf-8 -*-
"""Boards and their circuits read from Revit, the room or space each
fixture is in (in the architectural link, else in this model), and the
descriptions written to the circuits' Load Name."""
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, FilteredElementCollector, LocationCurve,
    LocationPoint, RevitLinkInstance, StorageType, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from circuitdesc.describe import LOAD_SLOTS, POWER_WIRING, Circuit, fill_unknown, label, number_text

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
        labels, fixtures = [], []
        if not feeder:
            for element in elements:
                key = id_int(element.Id)
                if key not in cache:
                    space = find_space(element, models)
                    cache[key] = (space_label(space, values["style"], values["upper"])
                                  if space is not None else None)
                labels.append(cache[key])
                fixtures.append((fixture_type(element), fixture_watts(element)))
        if any(watts is None for _, watts in fixtures):
            fixtures = fill_unknown(fixtures, circuit_watts(system))
        # without the Load parameters on the circuit the groups are not written
        has_loads = len(missing_load_params(system)) < LOAD_SLOTS * 3
        circuit = Circuit(system, name, system.CircuitNumber or u"", _slot(system),
                          system.LoadName, labels, feeder, fixtures,
                          read_loads(system) if has_loads else None,
                          is_power(elements), read_wiring(system))
        circuit.has_loads = has_loads
        out.append(circuit)
    return out


# ---------------------------------------------------------------- load groups

TYPE, NOS, WPU = "Type", "Nos", "WpU"
# fixture parameters holding its load, when Revit's own is not on it
LOAD_NAMES = ("Apparent Load", "Wattage", "Load", "Power", "Apparent Power", "Watts")


def _symbol(element):
    try:
        return element.Document.GetElement(element.GetTypeId())
    except Exception:
        return None


def fixture_type(element):
    """What the TYPE column says: the Type Comments of the fixture's type,
    else its type name."""
    symbol = _symbol(element)
    if symbol is None:
        return u""
    text = _bip_text(symbol, "ALL_MODEL_TYPE_COMMENTS").strip()
    if text:
        return text
    try:
        p = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        return (p.AsString() or u"").strip()
    except Exception:
        return u""


def _is_power(param):
    try:
        from Autodesk.Revit.DB import SpecTypeId
        spec = param.Definition.GetDataType()
        return spec in (SpecTypeId.ApparentPower, SpecTypeId.ElectricalPower,
                        SpecTypeId.Wattage)
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import ParameterType       # Revit 2021 and older
        return param.Definition.ParameterType in (
            ParameterType.ElectricalApparentPower, ParameterType.ElectricalPower,
            ParameterType.ElectricalWattage)
    except Exception:
        return False


def _to_watts(internal):
    try:
        from Autodesk.Revit.DB import UnitTypeId, UnitUtils
        return UnitUtils.ConvertFromInternalUnits(internal, UnitTypeId.Watts)
    except Exception:
        return internal * FEET ** 2


def _from_watts(watts):
    try:
        from Autodesk.Revit.DB import UnitTypeId, UnitUtils
        return UnitUtils.ConvertToInternalUnits(watts, UnitTypeId.Watts)
    except Exception:
        return watts / FEET ** 2


def _number(param):
    """The value of a number or text parameter, power in W; None when empty."""
    if param is None or not param.HasValue:
        return None
    if param.StorageType == StorageType.Double:
        value = param.AsDouble()
        return _to_watts(value) if _is_power(param) else value
    if param.StorageType == StorageType.Integer:
        return float(param.AsInteger())
    if param.StorageType == StorageType.String:
        text = (param.AsString() or u"").upper().replace("VA", "").replace("W", "")
        try:
            return float(text.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def connector_watts(element):
    """The Apparent Load set on the fixture's electrical connectors, in VA
    (W), None when it cannot be read (Revit 2017+)."""
    try:
        from Autodesk.Revit.DB import Domain, DoubleParameterValue
        connectors = element.MEPModel.ConnectorManager.Connectors
    except Exception:
        return None
    load_id = ElementId(BuiltInParameter.RBS_ELEC_APPARENT_LOAD)
    total = None
    for connector in connectors:
        try:
            if connector.Domain != Domain.DomainElectrical:
                continue
            value = connector.GetMEPConnectorInfo().GetConnectorParameterValue(load_id)
            if isinstance(value, DoubleParameterValue) and value.Value > 0:
                total = (total or 0.0) + _to_watts(value.Value)
        except Exception:
            continue
    return total


def fixture_watts(element):
    """The load of one fixture in W (VA): the Apparent Load of its
    connector, else a load parameter of the instance or its type."""
    value = connector_watts(element)
    if value:
        return value
    symbol = _symbol(element)
    for holder in (element, symbol):
        if holder is None:
            continue
        try:
            value = _number(holder.get_Parameter(BuiltInParameter.RBS_ELEC_APPARENT_LOAD))
            if value:
                return value
        except Exception:
            pass
    for holder in (element, symbol):
        if holder is None:
            continue
        for name in LOAD_NAMES:
            try:
                value = _number(holder.LookupParameter(name))
            except Exception:
                value = None
            if value:
                return value
    return None


def circuit_watts(system):
    """The circuit's apparent load in VA (W), None when not known."""
    try:
        value = _to_watts(system.ApparentLoad)
        return value if value > 0 else None
    except Exception:
        return _number(system.get_Parameter(BuiltInParameter.RBS_ELEC_APPARENT_LOAD))


def _load_param(system, i, part):
    return system.LookupParameter("Load%d_%s" % (i, part))


def missing_load_params(system):
    """Names of the Load1_Type ... Load6_WpU parameters not on the circuit."""
    return ["Load%d_%s" % (i, part) for i in range(1, LOAD_SLOTS + 1)
            for part in (TYPE, NOS, WPU) if _load_param(system, i, part) is None]


def _read_text(param, part):
    if param is None or not param.HasValue:
        return u""
    if part == TYPE or param.StorageType == StorageType.String:
        text = (param.AsString() or u"").strip()
        if part == TYPE:
            return text
        value = _number(param)
        return number_text(value) if value is not None else text
    value = _number(param)
    return number_text(value) if value else u""


def read_loads(system):
    """[(type, nos, W per unit)] typed on the circuit now."""
    return [tuple(_read_text(_load_param(system, i, part), part)
                  for part in (TYPE, NOS, WPU)) for i in range(1, LOAD_SLOTS + 1)]


def _set(param, text):
    """Write a Load parameter from its text; nothing to write clears it."""
    if param is None or param.IsReadOnly:
        return
    if param.StorageType == StorageType.String:
        param.Set(text)
        return
    if not text:
        try:
            param.ClearValue()
        except Exception:
            param.Set(0 if param.StorageType == StorageType.Integer else 0.0)
        return
    value = float(text)
    if param.StorageType == StorageType.Integer:
        param.Set(int(round(value)))
    elif param.StorageType == StorageType.Double:
        param.Set(_from_watts(value) if _is_power(param) else value)


LIGHTING = (BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices)


def is_power(elements):
    """A power circuit: fixtures connected and none of them lights."""
    if not elements:
        return False
    for element in elements:
        try:
            if id_int(element.Category.Id) in [int(c) for c in LIGHTING]:
                return False
        except Exception:
            return False
    return True


def read_wiring(system):
    """{name: text} of the wiring parameters on the circuit."""
    out = {}
    for name, _ in POWER_WIRING:
        param = system.LookupParameter(name)
        if param is None:
            continue
        if not param.HasValue:
            out[name] = u""
        elif param.StorageType == StorageType.String:
            out[name] = (param.AsString() or u"").strip()
        else:
            out[name] = number_text(_number(param)) if _number(param) else u""
    return out


def write_wiring(circuit):
    for name, text in circuit.wiring.items():
        if text == circuit.old_wiring.get(name):
            continue
        param = circuit.ref.LookupParameter(name)
        if param is None or param.IsReadOnly:
            continue
        if param.StorageType == StorageType.String:
            param.Set(text)
            continue
        try:
            value = float(text)
        except ValueError:
            continue                    # 27.8(5.4) does not go in a number
        if param.StorageType == StorageType.Integer:
            param.Set(int(round(value)))
        elif param.StorageType == StorageType.Double:
            param.Set(value)


def write_loads(circuit):
    for i, group in enumerate(circuit.loads, 1):
        for part, text in zip((TYPE, NOS, WPU), group):
            _set(_load_param(circuit.ref, i, part), text)


def write(circuits):
    """Write the new descriptions and load groups; [(circuit, error)] of
    those that failed."""
    failed = []
    for circuit in circuits:
        try:
            if circuit.new != circuit.old:
                _write_name(circuit)
            if circuit.loads_changed:
                write_loads(circuit)
            if circuit.wiring_changed:
                write_wiring(circuit)
        except Exception as error:
            failed.append((circuit, error))
    return failed


def _write_name(circuit):
    try:
        circuit.ref.LoadName = circuit.new
    except Exception:
        p = circuit.ref.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NAME)
        if p is None or p.IsReadOnly or not p.Set(circuit.new):
            raise Exception("Load Name is read only")
