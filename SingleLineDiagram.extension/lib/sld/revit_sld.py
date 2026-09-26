# -*- coding: utf-8 -*-
"""Revit side: read the electrical model and draw the diagram.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import datetime

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, CurveArray, ElementTypeGroup,
    FilteredElementCollector, HorizontalTextAlignment, Line, StorageType,
    TextNote, TextNoteOptions, Transaction, VerticalTextAlignment, View,
    ViewDrafting, ViewFamily, ViewFamilyType, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from sld.cables import (cable_from_revit_values, conductor_code, construction,
                        insulation_code)
from sld.layout import BOTTOM, CENTER, layout_diagram
from sld.model import CircuitInfo, EquipmentInfo, build_diagram

VIEW_NAME = "Single Line Diagram"

# Optional text parameter on circuits. When filled in, its value is printed
# as the cable description instead of the one generated from the circuit.
CABLE_OVERRIDE_PARAM = "SLD Cable"

# Outer sheath; Revit has no setting for it, so it is fixed here.
CABLE_SHEATH = "PVC"
INCHES_PER_FOOT = 12.0


def _param_text(element, bip):
    """Formatted parameter value (with units) or '' when missing/empty."""
    try:
        p = element.get_Parameter(bip)
    except Exception:
        return ""
    if p is None or not p.HasValue:
        return ""
    if p.StorageType == StorageType.String:
        value = p.AsString()
    else:
        value = p.AsValueString()
    return (value or "").strip()


def _equipment_name(element):
    return _param_text(element, BuiltInParameter.RBS_ELEC_PANEL_NAME) or element.Name


def _int_attr(obj, name, default=0):
    try:
        value = getattr(obj, name)
        return int(value) if value is not None else default
    except Exception:
        return default


def _cable_build(system):
    """'Cu/XLPE/PVC' from the circuit's wire type (material/insulation)."""
    material, insulation = "", ""
    try:
        wire_type = system.WireType
        if wire_type is not None:
            material = wire_type.WireMaterial.Name
            insulation = wire_type.Insulation.Name
    except Exception:
        pass
    return construction(conductor_code(material), insulation_code(insulation), CABLE_SHEATH)


def _cable_text(system, wire_size):
    """BS/IEC cable text, e.g. 4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC."""
    try:
        override = system.LookupParameter(CABLE_OVERRIDE_PARAM)
        if override is not None and override.HasValue and (override.AsString() or "").strip():
            return override.AsString().strip()
    except Exception:
        pass
    return cable_from_revit_values(
        hots=_int_attr(system, "HotConductorsNumber"),
        neutrals=_int_attr(system, "NeutralConductorsNumber"),
        grounds=_int_attr(system, "GroundConductorsNumber"),
        wire_size_text=wire_size,
        build=_cable_build(system),
        runs=_int_attr(system, "RunsNumber", 1),
    )


def extract(doc):
    """Collect EquipmentInfo/CircuitInfo lists from the model."""
    equipment = []
    ids = set()
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
                 .WhereElementIsNotElementType())
    for el in collector:
        details = [
            _param_text(el, BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM),
        ]
        mains = _param_text(el, BuiltInParameter.RBS_ELEC_MAINS)
        if mains:
            details.append("Mains: %s" % mains)
        total = _param_text(el, BuiltInParameter.RBS_ELEC_PANEL_TOTALLOAD_PARAM)
        if total:
            details.append("Load: %s" % total)
        equipment.append(EquipmentInfo(el.UniqueId, _equipment_name(el), details))
        ids.add(el.UniqueId)

    circuits = []
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        if system.SystemType != ElectricalSystemType.PowerCircuit:
            continue
        source = system.BaseEquipment
        if source is None:
            continue  # circuit not connected to a panel
        fed, branch_count = [], 0
        for el in system.Elements:
            if el.UniqueId in ids:
                fed.append(el.UniqueId)
            else:
                branch_count += 1
        wire_size = _param_text(system, BuiltInParameter.RBS_ELEC_CIRCUIT_WIRE_SIZE_PARAM)
        circuits.append(CircuitInfo(
            id=system.UniqueId,
            source_id=source.UniqueId,
            circuit_number=system.CircuitNumber,
            load_name=system.LoadName,
            rating=_param_text(system, BuiltInParameter.RBS_ELEC_CIRCUIT_RATING_PARAM),
            poles=_param_text(system, BuiltInParameter.RBS_ELEC_NUMBER_OF_POLES),
            voltage=_param_text(system, BuiltInParameter.RBS_ELEC_VOLTAGE),
            load=_param_text(system, BuiltInParameter.RBS_ELEC_APPARENT_LOAD),
            wire_size=wire_size,
            cable=_cable_text(system, wire_size),
            fed_equipment_ids=fed,
            branch_load_count=branch_count,
        ))
    return equipment, circuits


def _unique_view_name(doc, base):
    existing = set(v.Name for v in FilteredElementCollector(doc).OfClass(View))
    if base not in existing:
        return base
    i = 2
    while "%s %d" % (base, i) in existing:
        i += 1
    return "%s %d" % (base, i)


def _drafting_view_type(doc):
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if vft.ViewFamily == ViewFamily.Drafting:
            return vft
    raise Exception("No drafting view type found in this project.")


def _xyz(x_in, y_in):
    return XYZ(x_in / INCHES_PER_FOOT, y_in / INCHES_PER_FOOT, 0.0)


def render(doc, drawing, view_name=VIEW_NAME):
    """Create a new 1:1 drafting view and draw `drawing` into it.

    Must be called inside an open transaction. Returns the new view.
    """
    view = ViewDrafting.Create(doc, _drafting_view_type(doc).Id)
    view.Name = _unique_view_name(doc, view_name)
    view.Scale = 1  # 1:1 so layout inches == paper inches

    short = doc.Application.ShortCurveTolerance
    curves = CurveArray()
    for ln in drawing.lines:
        a, b = _xyz(ln.x1, ln.y1), _xyz(ln.x2, ln.y2)
        if a.DistanceTo(b) > short:
            curves.Append(Line.CreateBound(a, b))
    if not curves.IsEmpty:
        doc.Create.NewDetailCurveArray(view, curves)

    type_id = doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType)
    min_w = TextNote.GetMinimumAllowedWidth(doc, type_id)
    max_w = TextNote.GetMaximumAllowedWidth(doc, type_id)
    for t in drawing.texts:
        opts = TextNoteOptions(type_id)
        opts.HorizontalAlignment = (HorizontalTextAlignment.Center if t.align == CENTER
                                    else HorizontalTextAlignment.Left)
        opts.VerticalAlignment = (VerticalTextAlignment.Bottom if t.valign == BOTTOM
                                  else VerticalTextAlignment.Top)
        width = min(max(t.width / INCHES_PER_FOOT, min_w), max_w)
        TextNote.Create(doc, view.Id, _xyz(t.x, t.y), width, t.text, opts)
    return view


def generate(doc, include_branch_circuits=False):
    """Build and draw the diagram. Returns (view or None, diagram)."""
    equipment, circuits = extract(doc)
    diagram = build_diagram(equipment, circuits, include_branch_circuits)
    if not diagram.roots:
        return None, diagram

    project = doc.ProjectInformation.Name if doc.ProjectInformation else ""
    title = "SINGLE LINE DIAGRAM" + (" - %s" % project if project else "")
    subtitle = "Generated %s" % datetime.date.today().isoformat()
    drawing = layout_diagram(diagram, title, subtitle)

    t = Transaction(doc, "Generate Single Line Diagram")
    t.Start()
    try:
        view = render(doc, drawing)
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return view, diagram
