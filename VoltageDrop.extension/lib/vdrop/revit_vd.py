# -*- coding: utf-8 -*-
"""Revit side: read every power circuit as a voltage drop row, write the
results back and add the parameters used to type the lengths.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.

Parameters (instance, on Electrical Circuits and Electrical Equipment; the
tool adds them on first use):

  VD Length         cable length in metres, typed by you        Text
  VD Installation   Cable Tray / Duct Bank / Ground (optional)   Text
  VD Cable          e.g. 4x4Cx300 XLPE/SWA/PVC (optional)        Text
  VD Load kW        maximum demand load in kW (optional)         Text
  VD Percent        result: voltage drop of the cable (%)        Number
  VD Total Percent  result: cumulative voltage drop (%)          Number

On a main board with no supply circuit, VD Length / VD Cable / VD Load kW
describe the cable from the transformer.
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
P_VD = "VD Percent"
P_TOTAL = "VD Total Percent"
PARAMETERS = [(P_LENGTH, "text"), (P_INSTALLATION, "text"), (P_CABLE, "text"),
              (P_LOAD, "text"), (P_VD, "number"), (P_TOTAL, "number")]
PARAMETER_GROUP = "Voltage Drop"
SCHEDULE_NAME = "Voltage Drop Circuits"

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


# ---------------------------------------------------------------- equipment

class _Equipment(object):
    def __init__(self, element):
        self.element = element
        self.id = element.UniqueId
        self.name = (_bip_text(element, "RBS_ELEC_PANEL_NAME") or element.Name or "").strip()
        self.kind = _kind(element)
        self.demand_kva = _positive(_bip_double(element, "RBS_ELEC_PANEL_TOTALESTLOAD_PARAM"),
                                    INTERNAL_POWER / 1000.0)
        self.connected_kva = _positive(_bip_double(element, "RBS_ELEC_PANEL_TOTALLOAD_PARAM"),
                                       INTERNAL_POWER / 1000.0)
        self.mains = parse.number(_bip_text(element, "RBS_ELEC_MAINS"))
        self.phases = _phases(element)


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


def _phases(element):
    try:
        from Autodesk.Revit.DB.Electrical import ElectricalPhase
        dist = element.Document.GetElement(element.get_Parameter(
            BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM).AsElementId())
        if dist is not None and dist.ElectricalPhase == ElectricalPhase.SinglePhase:
            return 1
    except Exception:
        pass
    return 3


def _equipment(doc):
    out = {}
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
                 .WhereElementIsNotElementType())
    for el in collector:
        out[el.UniqueId] = _Equipment(el)
    return out


# ---------------------------------------------------------------- circuits

def _circuit_kind(system):
    try:
        from Autodesk.Revit.DB.Electrical import CircuitType
        return {CircuitType.Spare: "spare", CircuitType.Space: "space"}.get(system.CircuitType, "")
    except Exception:
        return ""


def _installation(element, notes):
    text = _text(element, P_INSTALLATION)
    value = parse.installation(text)
    if text and value is None:
        notes.append(u"VD Installation '%s' not understood" % text)
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


def _revit_cable(system, notes):
    hots = _attr(system, "HotConductorsNumber") or 0
    neutrals = _attr(system, "NeutralConductorsNumber") or 0
    text = _bip_text(system, "RBS_ELEC_CIRCUIT_WIRE_SIZE_PARAM")
    size = parse.metric_size(text)
    if size is None:
        notes.append(u"wire size '%s' is not in mm²" % text if text else "no wire size")
        return None
    return parse.Cable(runs=max(int(_attr(system, "RunsNumber") or 1), 1),
                       cores=int(hots + neutrals) or None, size=size)


def _loads(system, element, target, pf, values, notes):
    """(TCL kW, MDL kW or None)."""
    tcl = _positive(_attr(system, "TrueLoad"), INTERNAL_POWER / 1000.0)
    if tcl is None:
        apparent = _positive(_attr(system, "ApparentLoad"), INTERNAL_POWER / 1000.0)
        tcl = apparent * (pf or values["power_factor"]) if apparent else None
    text = _text(element, P_LOAD)
    typed = parse.number(text)
    if typed is not None and typed > 0:
        return tcl, typed
    if text:
        notes.append(u"VD Load kW '%s' not understood" % text)
    if values["load_basis"] == MDL and target is not None and target.demand_kva:
        return tcl, target.demand_kva * (pf or values["power_factor"])
    return tcl, None


class Model(object):
    """What was read: the rows, their Revit elements, and what was left out."""

    def __init__(self):
        self.feeders = []
        self.elements = {}        # feeder id -> element holding its results
        self.skipped = 0          # final circuits without VD Length
        self.warnings = []


def _circuit_feeder(system, equipment, values, model):
    source = equipment.get(system.BaseEquipment.UniqueId)
    if source is None:
        return
    fed = []
    try:
        fed = [equipment[e.UniqueId] for e in system.Elements
               if e.UniqueId in equipment and e.UniqueId != source.id]
    except Exception:
        pass
    target = fed[0] if fed else None
    notes = []
    length = _length(system, notes)
    if target is None and length is None and not notes:
        model.skipped += 1
        return
    poles = _attr(system, "PolesNumber") or 3
    pf = _attr(system, "PowerFactor")
    pf = pf if pf and 0 < pf <= 1 else None
    tcl, mdl = _loads(system, system, target, pf, values, notes)
    number = _attr(system, "CircuitNumber") or ""
    slot = _attr(system, "StartSlot")
    name = target.name if target else (_attr(system, "LoadName") or "CKT %s" % number)
    model.feeders.append(Feeder(
        id=system.UniqueId, source_id=source.id, source=source.name, target=name,
        target_id=target.id if target else None, length=length,
        phases=3 if poles >= 3 else 1,
        voltage=_positive(_attr(system, "Voltage"), INTERNAL_POWER),
        tcl_kw=tcl, mdl_kw=mdl, power_factor=pf,
        breaker=_positive(_attr(system, "Rating")),
        installation=_installation(system, notes),
        cable=_typed_cable(system, (P_CABLE, "SLD Cable"), notes) or _revit_cable(system, notes),
        source_kind=source.kind,
        order=(slot if slot and slot > 0 else 10 ** 6, natural_key(number)),
        ref=system.Id, notes=notes))
    model.elements[system.UniqueId] = system


def _incomer_feeder(board, values, model):
    """Transformer -> main board cable, typed on a board with no supply."""
    notes = []
    length = _length(board.element, notes)
    if length is None and not notes:
        return
    pf = values["power_factor"]
    typed = parse.number(_text(board.element, P_LOAD))
    demand = board.demand_kva * pf if board.demand_kva else None
    connected = board.connected_kva * pf if board.connected_kva else None
    mdl = typed if typed else (demand if values["load_basis"] == MDL else None)
    feeder_id = board.id + ":incomer"
    model.feeders.append(Feeder(
        id=feeder_id, source_id="%s:%s" % (TRANSFORMER_SOURCE, board.id),
        source=TRANSFORMER_SOURCE, target=board.name, target_id=board.id, length=length,
        phases=board.phases, tcl_kw=connected, mdl_kw=mdl, breaker=board.mains,
        installation=_installation(board.element, notes),
        cable=_typed_cable(board.element, (P_CABLE, "SLD Incoming Cable"), notes),
        source_kind=TRANSFORMER, ref=board.element.Id, notes=notes))
    model.elements[feeder_id] = board.element


def collect(doc, values):
    """Model with a Feeder per power circuit (feeders to boards always, final
    circuits when they have a VD Length) and per main board incomer."""
    model = Model()
    equipment = _equipment(doc)
    fed_ids = set()
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        try:
            if system.SystemType != ElectricalSystemType.PowerCircuit:
                continue
            if system.BaseEquipment is None or _circuit_kind(system):
                continue
            for e in system.Elements:
                if e.UniqueId in equipment and e.UniqueId != system.BaseEquipment.UniqueId:
                    fed_ids.add(e.UniqueId)
            _circuit_feeder(system, equipment, values, model)
        except Exception as error:
            model.warnings.append(u"Circuit %s skipped: %s" % (
                _attr(system, "CircuitNumber") or "?", error))
    for board in equipment.values():
        if board.kind == BOARD and board.id not in fed_ids:
            _incomer_feeder(board, values, model)
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

def missing_parameters(doc):
    names = set()
    iterator = doc.ParameterBindings.ForwardIterator()
    while iterator.MoveNext():
        names.add(iterator.Key.Name)
    return [name for name, _ in PARAMETERS if name not in names]


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


def _bind(doc, definition, binding):
    try:
        from Autodesk.Revit.DB import GroupTypeId
        return doc.ParameterBindings.Insert(definition, binding, GroupTypeId.Electrical)
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import BuiltInParameterGroup
        return doc.ParameterBindings.Insert(definition, binding,
                                            BuiltInParameterGroup.PG_ELECTRICAL)
    except Exception:
        return doc.ParameterBindings.Insert(definition, binding)


def _add_parameters(doc, names):
    """Shared parameters bound to circuits and equipment. The shared
    parameter file is a temporary one; the user's own file is restored."""
    app = doc.Application
    previous = app.SharedParametersFilename
    path = os.path.join(tempfile.gettempdir(), "VoltageDrop_parameters.txt")
    open(path, "w").close()
    app.SharedParametersFilename = path
    try:
        group = app.OpenSharedParameterFile().Groups.Create(PARAMETER_GROUP)
        categories = app.Create.NewCategorySet()
        for bic in (BuiltInCategory.OST_ElectricalCircuit, BuiltInCategory.OST_ElectricalEquipment):
            categories.Insert(Category.GetCategory(doc, bic))
        binding = app.Create.NewInstanceBinding(categories)
        for name, kind in PARAMETERS:
            if name in names:
                _bind(doc, group.Definitions.Create(_creation_options(name, kind)), binding)
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


def _schedule(doc):
    """'Voltage Drop Circuits' schedule: panel, circuit, load name, rating,
    wire size and the VD parameters, sorted by panel and circuit."""
    from Autodesk.Revit.DB import ScheduleSortGroupField, ViewSchedule
    for view in FilteredElementCollector(doc).OfClass(ViewSchedule):
        if view.Name == SCHEDULE_NAME:
            return view
    schedule = ViewSchedule.CreateSchedule(doc, ElementId(BuiltInCategory.OST_ElectricalCircuit))
    schedule.Name = SCHEDULE_NAME
    definition = schedule.Definition
    fields = list(definition.GetSchedulableFields())
    added = {}
    for bip_name in ("RBS_ELEC_CIRCUIT_PANEL_PARAM", "RBS_ELEC_CIRCUIT_NUMBER",
                     "RBS_ELEC_CIRCUIT_NAME", "RBS_ELEC_CIRCUIT_RATING_PARAM",
                     "RBS_ELEC_CIRCUIT_WIRE_SIZE_PARAM"):
        field = _schedulable(doc, fields, bip_name=bip_name)
        if field is not None:
            added[bip_name] = definition.AddField(field)
    for name, _ in PARAMETERS:
        field = _schedulable(doc, fields, name=name)
        if field is not None:
            definition.AddField(field)
    for bip_name in ("RBS_ELEC_CIRCUIT_PANEL_PARAM", "RBS_ELEC_CIRCUIT_NUMBER"):
        if bip_name in added:
            definition.AddSortGroupField(ScheduleSortGroupField(added[bip_name].FieldId))
    return schedule


def setup(doc, missing):
    """Add the missing parameters and the circuits schedule (one undo).
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
