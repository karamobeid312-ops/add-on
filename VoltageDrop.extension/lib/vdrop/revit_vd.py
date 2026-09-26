# -*- coding: utf-8 -*-
"""Revit side: read the incoming cable of every panel from the panel, write
the results back on it, and add the parameters used to type the lengths.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.

For each panel (board, DB, transformer, UPS) the row of its incoming cable
comes from the panel: FROM = the board supplying it, breaker = MCB Rating
(else Mains), loads = Total Estimated Demand / Total Connected, power factor
= VD PF typed on it, else true / apparent load of its circuits, phases =
its distribution system (and its voltage, if VD Settings says to use the
model's voltages), and what is typed on it. The circuit
feeding it is only used for what the panel doesn't give (the wire size,
which Revit keeps only on the circuit, or a value typed on the circuit).

Final circuits (fixtures, mechanical equipment) are calculated when a
length is typed on their loads (the longest one counts) or on the circuit.

Parameters (instance; the tool adds them on first use):

  VD Length         cable length in metres               Text    panels, circuits, loads
  VD Installation   Cable Tray / Duct Bank / Ground      Text    panels, circuits
  VD Cable          e.g. 4x4Cx300 XLPE/SWA/PVC           Text    panels, circuits
  VD Load kW        maximum demand load in kW            Text    panels, circuits
  VD PF             power factor, e.g. 0.9               Text    panels, circuits
  VD Percent        result: V.D of the incoming cable    Number  panels, circuits
  VD Total Percent  result: cumulative V.D               Number  panels, circuits

On a main board with no supply circuit, VD Length / VD Cable describe the
cable from the transformer.
"""
from __future__ import division

import os
import tempfile

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, Category, ElementId,
                               FilteredElementCollector, StorageType, Transaction)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from vdrop import parse
from vdrop.calc import BOARD, MDL, TRANSFORMER, UPS, Feeder, natural_key

P_LENGTH = "VD Length"
P_INSTALLATION = "VD Installation"
P_CABLE = "VD Cable"
P_LOAD = "VD Load kW"
P_PF = "VD PF"
P_VD = "VD Percent"
P_TOTAL = "VD Total Percent"
# Where each parameter goes. Lengths can also be typed on the loads of final
# circuits (fixtures, mechanical equipment).
_ON_PANELS = ("OST_ElectricalEquipment", "OST_ElectricalCircuit")
_ON_LOADS = _ON_PANELS + ("OST_ElectricalFixtures", "OST_LightingFixtures",
                          "OST_MechanicalEquipment")
PARAMETERS = [(P_LENGTH, "text", _ON_LOADS), (P_INSTALLATION, "text", _ON_PANELS),
              (P_CABLE, "text", _ON_PANELS), (P_LOAD, "text", _ON_PANELS),
              (P_PF, "text", _ON_PANELS),
              (P_VD, "number", _ON_PANELS), (P_TOTAL, "number", _ON_PANELS)]
PARAMETER_GROUP = "Voltage Drop"
SCHEDULE_NAME = "Voltage Drop Panels"

# Revit stores power and voltage in kg.ft²/s³ (and per A): 1 unit = 0.3048² W.
INTERNAL_POWER = 0.3048 ** 2
FEET = 0.3048
TRANSFORMER_SOURCE = "TR"


# ---------------------------------------------------------------- parameters

def _parameter(element, name):
    try:
        p = element.LookupParameter(name)
        return p if p is not None and p.HasValue else None
    except Exception:
        return None


def _text(element, name):
    p = _parameter(element, name)
    if p is None:
        return ""
    try:
        if p.StorageType == StorageType.String:
            return (p.AsString() or "").strip()
        return (p.AsValueString() or "").strip()
    except Exception:
        return ""


def _is_length(p):
    try:
        from Autodesk.Revit.DB import SpecTypeId
        return p.Definition.GetDataType() == SpecTypeId.Length
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import ParameterType
        return p.Definition.ParameterType == ParameterType.Length
    except Exception:
        return False


def _length(element, notes):
    """VD Length in metres, from a Text, Number or Length parameter."""
    p = _parameter(element, P_LENGTH)
    if p is None:
        return None
    try:
        if p.StorageType == StorageType.Double:
            value = p.AsDouble() * (FEET if _is_length(p) else 1.0)
            return value if value > 0 else None
    except Exception:
        return None
    text = _text(element, P_LENGTH)
    value = parse.length_m(text)
    if value is None and text:
        notes.append(u"VD Length '%s' not understood" % text)
    return value


def _bip(element, name):
    """Built-in parameter by name (None when this Revit lacks it)."""
    bip = getattr(BuiltInParameter, name, None)
    if bip is None:
        return None
    try:
        p = element.get_Parameter(bip)
        return p if p is not None and p.HasValue else None
    except Exception:
        return None


def _bip_double(element, name):
    p = _bip(element, name)
    try:
        return p.AsDouble() if p is not None else None
    except Exception:
        return None


def _bip_text(element, name):
    p = _bip(element, name)
    if p is None:
        return ""
    try:
        value = p.AsString() if p.StorageType == StorageType.String else p.AsValueString()
        return (value or "").strip()
    except Exception:
        return ""


def _attr(obj, name):
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _positive(value, factor=1.0):
    try:
        value = float(value) * factor
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _id_int(element_id):
    try:
        return element_id.Value            # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


# ---------------------------------------------------------------- panels

class _Equipment(object):
    """A panel (or transformer / UPS): its own values and what is typed on it."""

    def __init__(self, element):
        self.element = element
        self.id = element.UniqueId
        self.name = (_bip_text(element, "RBS_ELEC_PANEL_NAME") or element.Name or "").strip()
        self.kind = _kind(element)
        self.demand_kva = _positive(_bip_double(element, "RBS_ELEC_PANEL_TOTALESTLOAD_PARAM"),
                                    INTERNAL_POWER / 1000.0)
        self.connected_kva = _positive(_bip_double(element, "RBS_ELEC_PANEL_TOTALLOAD_PARAM"),
                                       INTERNAL_POWER / 1000.0)
        # the breaker of the incoming cable: MCB Rating, else Mains (A)
        self.breaker = (_positive(_bip_double(element, "RBS_ELEC_PANEL_MCB_RATING_PARAM")) or
                        _positive(_bip_double(element, "RBS_ELEC_MAINS")))
        dist = _distribution(element)
        self.phases = _phases(dist)
        self.voltage = _voltage(dist, self.phases)
        self.true_kw = 0.0            # sum of the loads of its circuits
        self.apparent_kva = 0.0

    @property
    def load_pf(self):
        """Power factor of everything the panel feeds, None when unloaded."""
        if self.apparent_kva > 0 and self.true_kw > 0:
            return min(self.true_kw / self.apparent_kva, 1.0)
        return None


def _kind(element):
    symbol = _text(element, "SLD Symbol").upper()
    if symbol in ("TRANSFORMER", "TR"):
        return TRANSFORMER
    if symbol == "UPS":
        return UPS
    family = ""
    try:
        family = element.Symbol.Family.Name.upper()
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import PartType
        part = element.Symbol.Family.get_Parameter(
            BuiltInParameter.FAMILY_CONTENT_PART_TYPE).AsInteger()
        if part == int(PartType.Transformer):
            return TRANSFORMER
    except Exception:
        pass
    if "TRANSFORMER" in family:
        return TRANSFORMER
    if "UPS" in family:
        return UPS
    return BOARD


def _distribution(element):
    """The panel's distribution system (a transformer's primary side)."""
    try:
        return element.Document.GetElement(element.get_Parameter(
            BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM).AsElementId())
    except Exception:
        return None


def _phases(dist):
    try:
        from Autodesk.Revit.DB.Electrical import ElectricalPhase
        if dist is not None and dist.ElectricalPhase == ElectricalPhase.SinglePhase:
            return 1
    except Exception:
        pass
    return 3


def _voltage(dist, phases):
    """Line to line voltage (three phase) or line to ground (single phase), V."""
    try:
        voltage = dist.VoltageLineToLine if phases == 3 else dist.VoltageLineToGround
        return parse.volts(voltage.ActualValue)
    except Exception:
        return None


def _equipment(doc):
    out = {}
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
                 .WhereElementIsNotElementType())
    for el in collector:
        out[el.UniqueId] = _Equipment(el)
    return out


# ---------------------------------------------------------------- typed values

def _circuit_kind(system):
    try:
        from Autodesk.Revit.DB.Electrical import CircuitType
        return {CircuitType.Spare: "spare", CircuitType.Space: "space"}.get(system.CircuitType, "")
    except Exception:
        return ""


def _first(elements, read, notes):
    """First value found by read(element, notes) on the elements, in order."""
    for element in elements:
        if element is None:
            continue
        before = len(notes)
        value = read(element, notes)
        if value is not None or len(notes) > before:
            return value
    return None


def _installation(element, notes):
    text = _text(element, P_INSTALLATION)
    value = parse.installation(text)
    if text and value is None:
        notes.append(u"VD Installation '%s' not understood" % text)
    return value


def _typed_load(element, notes):
    text = _text(element, P_LOAD)
    value = parse.number(text)
    if value is not None and value > 0:
        return value
    if text:
        notes.append(u"VD Load kW '%s' not understood" % text)
    return None


def _typed_pf(element, notes):
    text = _text(element, P_PF)
    value = parse.power_factor(text)
    if text and value is None:
        notes.append(u"VD PF '%s' not understood" % text)
    return value


def _typed_cable(element, names, notes):
    """Cable typed in VD Cable (or the SLD's cable override)."""
    for name in names:
        text = _text(element, name)
        if not text:
            continue
        cable = parse.cable(text)
        if cable is not None:
            return cable
        if name == P_CABLE:
            notes.append(u"VD Cable '%s' not understood" % text)
            return None
    return None


def _revit_cable(system, notes):
    """Cable from the circuit's wire size, the only place Revit keeps it."""
    if system is None:
        return None
    hots = _attr(system, "HotConductorsNumber") or 0
    neutrals = _attr(system, "NeutralConductorsNumber") or 0
    text = _bip_text(system, "RBS_ELEC_CIRCUIT_WIRE_SIZE_PARAM")
    size = parse.metric_size(text)
    if size is None:
        notes.append(u"wire size '%s' is not in mm²" % text if text else "no wire size")
        return None
    return parse.Cable(runs=max(int(_attr(system, "RunsNumber") or 1), 1),
                       cores=int(hots + neutrals) or None, size=size)


def _circuit_number(system, bip_name, attr):
    """A circuit value from its parameter (always in Revit's internal units),
    else from the ElectricalSystem property."""
    value = _bip_double(system, bip_name)
    return value if value is not None else _attr(system, attr)


def _circuit_loads(system):
    """(true load kW, apparent load kVA) of a circuit, None when missing."""
    kilo = INTERNAL_POWER / 1000.0
    return (_positive(_circuit_number(system, "RBS_ELEC_TRUE_LOAD", "TrueLoad"), kilo),
            _positive(_circuit_number(system, "RBS_ELEC_APPARENT_LOAD", "ApparentLoad"), kilo))


def _circuit_values(system):
    """(power factor, TCL kW, voltage, rating) of a circuit, None when missing.
    The power factor is true load / apparent load, else Revit's value."""
    true, apparent = _circuit_loads(system)
    if true and apparent:
        pf = min(true / apparent, 1.0)
    else:
        pf = _attr(system, "PowerFactor")
        pf = pf if pf and 0 < pf <= 1 else None
    tcl = true if true else (apparent * (pf or 1.0) if apparent else None)
    return (pf, tcl, parse.volts(_circuit_number(system, "RBS_ELEC_VOLTAGE", "Voltage")),
            _positive(_circuit_number(system, "RBS_ELEC_CIRCUIT_RATING_PARAM", "Rating")))


def _model_voltage(values, voltage):
    """The model's voltage when VD Settings says so; None means the VD
    Settings voltage (400 V three phase, 230 V single phase)."""
    return voltage if values.get("voltage_source") == "model" else None


def _order(system):
    if system is None:
        return None
    number = _attr(system, "CircuitNumber") or ""
    slot = _attr(system, "StartSlot")
    return (slot if slot and slot > 0 else 10 ** 6, natural_key(number))


class Model(object):
    """What was read: the rows, their Revit elements, and what was left out."""

    def __init__(self):
        self.feeders = []
        self.elements = {}        # feeder id -> element holding its results
        self.skipped = 0          # final circuits without VD Length
        self.warnings = []


# ---------------------------------------------------------------- rows

def _panel_feeder(panel, system, source, values, model):
    """The cable feeding a panel, read from the panel. The circuit feeding it
    (None for a main board fed straight from the transformer) is only used
    for what the panel doesn't give."""
    el = panel.element
    typed = [el, system]          # typed on the panel, else on the circuit
    notes = []
    length = _first(typed, _length, notes)
    circuit_pf, circuit_tcl, circuit_voltage, rating = (
        _circuit_values(system) if system is not None else (None, None, None, None))
    # typed on the panel (or its circuit), else the panel's own loads
    pf = _first(typed, _typed_pf, notes) or panel.load_pf or circuit_pf
    pf_used = pf or values["power_factor"]
    tcl = panel.connected_kva * pf_used if panel.connected_kva else circuit_tcl
    mdl = _first(typed, _typed_load, notes)
    if mdl is None and values["load_basis"] == MDL and panel.demand_kva:
        mdl = panel.demand_kva * pf_used
    cable = (_typed_cable(el, (P_CABLE, "SLD Incoming Cable"), notes) or
             (_typed_cable(system, (P_CABLE, "SLD Cable"), notes) if system is not None else None))
    if cable is None and not [n for n in notes if n.startswith("VD Cable")]:
        cable = _revit_cable(system, notes)
    if source is None:
        source_id, source_name, kind = "%s:%s" % (TRANSFORMER_SOURCE, panel.id), TRANSFORMER_SOURCE, TRANSFORMER
    else:
        source_id, source_name, kind = source.id, source.name, source.kind
    model.feeders.append(Feeder(
        id=panel.id, source_id=source_id, source=source_name, target=panel.name,
        target_id=panel.id, length=length, phases=panel.phases,
        voltage=_model_voltage(values, panel.voltage or circuit_voltage),
        tcl_kw=tcl, mdl_kw=mdl, power_factor=pf,
        breaker=panel.breaker or rating, installation=_first(typed, _installation, notes),
        cable=cable, source_kind=kind, order=_order(system), ref=el.Id, notes=notes))
    model.elements[panel.id] = el


def _longest(loads, notes):
    """Longest VD Length typed on the fixtures / equipment of a circuit."""
    lengths = [_length(e, notes) for e in loads]
    lengths = [l for l in lengths if l is not None]
    return max(lengths) if lengths else None


def _final_feeder(system, source, loads, values, model):
    """A circuit to fixtures or equipment: length from the farthest one (or
    typed on the circuit), the rest from the circuit."""
    notes = []
    length = _longest(loads, notes)
    if length is None and not notes:
        length = _length(system, notes)
    if length is None and not notes:
        model.skipped += 1
        return
    circuit_pf, tcl, voltage, rating = _circuit_values(system)
    pf = _typed_pf(system, notes) or circuit_pf
    poles = _attr(system, "PolesNumber") or 3
    number = _attr(system, "CircuitNumber") or ""
    model.feeders.append(Feeder(
        id=system.UniqueId, source_id=source.id, source=source.name,
        target=_attr(system, "LoadName") or "CKT %s" % number, length=length,
        phases=3 if poles >= 3 else 1, voltage=_model_voltage(values, voltage), tcl_kw=tcl,
        mdl_kw=_typed_load(system, notes), power_factor=pf, breaker=rating,
        installation=_installation(system, notes),
        cable=_typed_cable(system, (P_CABLE, "SLD Cable"), notes) or _revit_cable(system, notes),
        source_kind=source.kind, order=_order(system), ref=system.Id, notes=notes))
    model.elements[system.UniqueId] = system


def collect(doc, values):
    """Model with a row for the incoming cable of every panel (read from the
    panel) and for every final circuit with a length."""
    model = Model()
    equipment = _equipment(doc)
    feeding = {}      # panel id -> (circuit, source panel)
    finals = []
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        try:
            if system.SystemType != ElectricalSystemType.PowerCircuit:
                continue
            if system.BaseEquipment is None or _circuit_kind(system):
                continue
            source = equipment.get(system.BaseEquipment.UniqueId)
            if source is None:
                continue
            true, apparent = _circuit_loads(system)
            source.true_kw += true or 0.0
            source.apparent_kva += apparent or 0.0
            elements = list(system.Elements)
            panels = [e.UniqueId for e in elements
                      if e.UniqueId in equipment and e.UniqueId != source.id]
            for panel_id in panels:
                if panel_id in feeding:
                    model.warnings.append("%s is fed by more than one circuit; using the one "
                                          "from %s." % (equipment[panel_id].name,
                                                        feeding[panel_id][1].name))
                else:
                    feeding[panel_id] = (system, source)
            if not panels:
                finals.append((system, source, elements))
        except Exception as error:
            model.warnings.append(u"Circuit %s skipped: %s" % (
                _attr(system, "CircuitNumber") or "?", error))

    for panel in equipment.values():
        try:
            if panel.id in feeding:
                system, source = feeding[panel.id]
                _panel_feeder(panel, system, source, values, model)
            elif panel.kind == BOARD:
                # main board fed straight from the transformer: a row only
                # when its incoming cable is described on it
                notes = []
                if _length(panel.element, notes) is not None or notes:
                    _panel_feeder(panel, None, None, values, model)
        except Exception as error:
            model.warnings.append(u"%s skipped: %s" % (panel.name, error))
    for system, source, loads in finals:
        try:
            _final_feeder(system, source, loads, values, model)
        except Exception as error:
            model.warnings.append(u"Circuit %s skipped: %s" % (
                _attr(system, "CircuitNumber") or "?", error))
    return model


# ---------------------------------------------------------------- results

def _set_number(element, name, value):
    try:
        p = element.LookupParameter(name)
    except Exception:
        return False
    if p is None or p.IsReadOnly:
        return False
    try:
        if value is None:
            if p.HasValue and hasattr(p, "ClearValue"):
                p.ClearValue()
            return True
        if p.StorageType == StorageType.Double:
            p.Set(round(float(value), 3))
        elif p.StorageType == StorageType.String:
            p.Set(parse.format_number(value))
        else:
            return False
        return True
    except Exception:
        return False


def write_results(doc, result, elements):
    """VD Percent / VD Total Percent on every row's element. Returns how
    many elements got a value (0 when the parameters are missing)."""
    pairs = [(elements[r.feeder.id], r) for r in result.rows() if r.feeder.id in elements]
    if not any(el.LookupParameter(P_VD) is not None for el, _ in pairs):
        return 0
    t = Transaction(doc, "Voltage Drop Results")
    t.Start()
    try:
        written = 0
        for element, row in pairs:
            done = _set_number(element, P_VD, row.vd_percent)
            done = _set_number(element, P_TOTAL, row.total_percent) or done
            written += 1 if done else 0
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return written


# ---------------------------------------------------------------- setup

def _bindings(doc):
    """{parameter name: (definition, binding)} of the project parameters."""
    out = {}
    iterator = doc.ParameterBindings.ForwardIterator()
    while iterator.MoveNext():
        out[iterator.Key.Name] = (iterator.Key, iterator.Current)
    return out


def _categories(doc, names):
    out = []
    for name in names:
        try:
            category = Category.GetCategory(doc, getattr(BuiltInCategory, name))
        except Exception:
            category = None
        if category is not None:
            out.append(category)
    return out


def missing_parameters(doc):
    """VD parameters not in the project, or not on all their categories."""
    bound = _bindings(doc)
    out = []
    for name, _, categories in PARAMETERS:
        if name not in bound:
            out.append(name)
            continue
        try:
            on = bound[name][1].Categories
            if any(not on.Contains(c) for c in _categories(doc, categories)):
                out.append(name)
        except Exception:
            pass
    return out


def _creation_options(name, kind):
    from Autodesk.Revit.DB import ExternalDefinitionCreationOptions
    try:
        from Autodesk.Revit.DB import SpecTypeId
        spec = SpecTypeId.String.Text if kind == "text" else SpecTypeId.Number
        return ExternalDefinitionCreationOptions(name, spec)
    except Exception:
        from Autodesk.Revit.DB import ParameterType
        ptype = ParameterType.Text if kind == "text" else ParameterType.Number
        return ExternalDefinitionCreationOptions(name, ptype)


def _bind(doc, definition, binding, again=False):
    """Insert (or, with again, re-insert) a binding in the Electrical group."""
    bindings = doc.ParameterBindings
    insert = bindings.ReInsert if again else bindings.Insert
    try:
        from Autodesk.Revit.DB import GroupTypeId
        return insert(definition, binding, GroupTypeId.Electrical)
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import BuiltInParameterGroup
        return insert(definition, binding, BuiltInParameterGroup.PG_ELECTRICAL)
    except Exception:
        return insert(definition, binding)


def _add_parameters(doc, names):
    """Shared parameters for `names` bound to their categories; the ones
    already in the project get the categories they lack. The shared
    parameter file is a temporary one; the user's own file is restored."""
    app = doc.Application
    bound = _bindings(doc)
    for name, _, categories in PARAMETERS:
        if name in names and name in bound:
            definition, binding = bound[name]
            for category in _categories(doc, categories):
                if not binding.Categories.Contains(category):
                    binding.Categories.Insert(category)
            _bind(doc, definition, binding, again=True)
    new = [p for p in PARAMETERS if p[0] in names and p[0] not in bound]
    if not new:
        return
    previous = app.SharedParametersFilename
    path = os.path.join(tempfile.gettempdir(), "VoltageDrop_parameters.txt")
    open(path, "w").close()
    app.SharedParametersFilename = path
    try:
        group = app.OpenSharedParameterFile().Groups.Create(PARAMETER_GROUP)
        for name, kind, categories in new:
            category_set = app.Create.NewCategorySet()
            for category in _categories(doc, categories):
                category_set.Insert(category)
            _bind(doc, group.Definitions.Create(_creation_options(name, kind)),
                  app.Create.NewInstanceBinding(category_set))
    finally:
        try:
            app.SharedParametersFilename = previous or ""
        except Exception:
            pass


def _schedulable(doc, fields, bip_name=None, name=None):
    wanted = None
    if bip_name:
        bip = getattr(BuiltInParameter, bip_name, None)
        if bip is None:
            return None
        wanted = _id_int(ElementId(bip))
    for field in fields:
        try:
            if wanted is not None and _id_int(field.ParameterId) == wanted:
                return field
            if name is not None and field.GetName(doc) == name:
                return field
        except Exception:
            continue
    return None


# Panel Name, Supply From, MCB Rating, Mains, Total Estimated Demand
_PANEL_FIELDS = ("RBS_ELEC_PANEL_NAME", "RBS_ELEC_PANEL_SUPPLY_FROM_PARAM",
                 "RBS_ELEC_PANEL_MCB_RATING_PARAM", "RBS_ELEC_MAINS",
                 "RBS_ELEC_PANEL_TOTALESTLOAD_PARAM")


def _schedule(doc):
    """'Voltage Drop Panels' schedule: every panel with its supply, breaker,
    demand load and the VD parameters, sorted by panel name."""
    from Autodesk.Revit.DB import ScheduleSortGroupField, ViewSchedule
    for view in FilteredElementCollector(doc).OfClass(ViewSchedule):
        if view.Name == SCHEDULE_NAME:
            _add_missing_fields(doc, view)
            return view
    schedule = ViewSchedule.CreateSchedule(doc, ElementId(BuiltInCategory.OST_ElectricalEquipment))
    schedule.Name = SCHEDULE_NAME
    definition = schedule.Definition
    fields = list(definition.GetSchedulableFields())
    added = {}
    for bip_name in _PANEL_FIELDS:
        field = _schedulable(doc, fields, bip_name=bip_name)
        if field is not None:
            added[bip_name] = definition.AddField(field)
    for name, _, _ in PARAMETERS:
        field = _schedulable(doc, fields, name=name)
        if field is not None:
            definition.AddField(field)
    if "RBS_ELEC_PANEL_NAME" in added:
        definition.AddSortGroupField(ScheduleSortGroupField(added["RBS_ELEC_PANEL_NAME"].FieldId))
    return schedule


def _add_missing_fields(doc, schedule):
    """VD parameters added since the schedule was made (e.g. VD PF)."""
    definition = schedule.Definition
    present = set()
    for i in range(definition.GetFieldCount()):
        try:
            present.add(definition.GetField(i).GetName())
        except Exception:
            pass
    fields = list(definition.GetSchedulableFields())
    for name, _, _ in PARAMETERS:
        if name not in present:
            field = _schedulable(doc, fields, name=name)
            if field is not None:
                definition.AddField(field)


def setup(doc, missing):
    """Add the missing parameters (one undo) and the panels schedule.
    Returns the schedule, or None if it could not be made."""
    t = Transaction(doc, "Voltage Drop Parameters")
    t.Start()
    try:
        _add_parameters(doc, missing)
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    t = Transaction(doc, "Voltage Drop Schedule")
    t.Start()
    try:
        schedule = _schedule(doc)
        t.Commit()
        return schedule
    except Exception:
        t.RollBack()
        return None


def project_info(doc):
    """Title block values from Revit's Project Information."""
    out = {}
    try:
        info = doc.ProjectInformation
    except Exception:
        return out
    for key, attr in (("project", "Name"), ("location", "Address"), ("client", "ClientName"),
                      ("block", "BuildingName"), ("status", "Status")):
        try:
            out[key] = (getattr(info, attr) or "").strip()
        except Exception:
            out[key] = ""
    return out
