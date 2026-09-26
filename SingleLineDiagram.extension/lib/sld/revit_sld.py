# -*- coding: utf-8 -*-
"""Revit side: read the electrical model and draw the LV schematic.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.

Optional parameters (project or shared, type Text) refine the drawing:

  Electrical Equipment
    SLD Symbol          MAIN / BOARD / DB / UPS / TRANSFORMER (force a symbol)
    SLD Form            e.g. "FORM 2b" or "FORM4-TYPE6"
    SLD Ways            e.g. "18"
    SLD Location        e.g. "ELEC. ROOM GF-48" (default: room name + number)
    SLD Description     transformer text, one item per line
                        (e.g. "11/0.4kV", "1000KVA", "OIL TYPE", "TRANSFORMER")
    SLD Incoming Cable  main board incoming cable, e.g. "7 SC 630mm² Cu/XLPE/AWA/PVC"
  Electrical Circuits
    SLD Cable           cable text printed exactly as typed
    SLD Symbol          ISOLATOR / DB / SPARE / PFC (force the way symbol)
"""
from __future__ import division


from Autodesk.Revit.DB import (
    Arc, BuiltInCategory, BuiltInParameter, CurveArray, ElementId,
    ElementTypeGroup, FilteredElementCollector, HorizontalTextAlignment, Line,
    StorageType, TextNote, TextNoteOptions, TextNoteType, Transaction,
    VerticalTextAlignment, View, ViewDrafting, ViewFamily, ViewFamilyType, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from sld import style
from sld.cables import (cable_from_revit_values, conductor_code, construction,
                        insulation_code)
from sld.geometry import CENTER, MIDDLE, RIGHT, TOP, line_length
from sld.layout import LayoutSettings, layout_schematic
from sld.model import CircuitInfo, EquipmentInfo, build_schematic

VIEW_NAME = "LV Schematic Diagram"
MM_PER_FOOT = 304.8

# Outer sheath; Revit has no setting for it, so it is fixed here.
CABLE_SHEATH = "PVC"


# ---------------------------------------------------------------- parameters

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


def _lookup(element, name):
    """Value of a named (project/shared) parameter as text, or ''."""
    try:
        p = element.LookupParameter(name)
        if p is None or not p.HasValue:
            return ""
        if p.StorageType == StorageType.String:
            return (p.AsString() or "").strip()
        return (p.AsValueString() or "").strip()
    except Exception:
        return ""


def _int_attr(obj, name, default=0):
    try:
        value = getattr(obj, name)
        return int(value) if value is not None else default
    except Exception:
        return default


# ---------------------------------------------------------------- equipment

def _equipment_name(element):
    return _param_text(element, BuiltInParameter.RBS_ELEC_PANEL_NAME) or element.Name


def _level(doc, element):
    level_id = getattr(element, "LevelId", None)
    if level_id is None or level_id == ElementId.InvalidElementId:
        try:
            level_id = element.get_Parameter(
                BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM).AsElementId()
        except Exception:
            level_id = None
    level = doc.GetElement(level_id) if level_id is not None else None
    if level is None:
        return "", 0.0
    try:
        return level.Name, level.Elevation
    except Exception:
        return level.Name, 0.0


def _location(element):
    override = _lookup(element, "SLD Location")
    if override:
        return override.upper()
    try:
        room = element.Room
    except Exception:
        room = None
    if room is None:
        return ""
    name = _param_text(room, BuiltInParameter.ROOM_NAME)
    number = _param_text(room, BuiltInParameter.ROOM_NUMBER)
    return " ".join(p for p in (name, number) if p).upper()


def _family_name(element):
    try:
        return element.Symbol.Family.Name
    except Exception:
        return ""


def _part_type(element):
    try:
        from Autodesk.Revit.DB import PartType
        value = element.Symbol.Family.get_Parameter(
            BuiltInParameter.FAMILY_CONTENT_PART_TYPE).AsInteger()
        if value == int(PartType.Transformer):
            return "transformer"
        if value == int(PartType.SwitchBoard):
            return "switchboard"
        if value == int(PartType.PanelBoard):
            return "panelboard"
    except Exception:
        pass
    return ""


def _phases(doc, element):
    try:
        from Autodesk.Revit.DB.Electrical import ElectricalPhase
        dist_id = element.get_Parameter(
            BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM).AsElementId()
        dist = doc.GetElement(dist_id)
        if dist is not None and dist.ElectricalPhase == ElectricalPhase.SinglePhase:
            return 1
    except Exception:
        pass
    return 3


def _ways(element, phases):
    declared = _lookup(element, "SLD Ways")
    if declared:
        return declared
    try:
        poles = element.get_Parameter(BuiltInParameter.RBS_ELEC_MAX_POLE_BREAKERS).AsInteger()
        if poles:
            return str(poles // phases if phases == 3 else poles)
    except Exception:
        pass
    return None


def _description(element, part_type):
    text = _lookup(element, "SLD Description")
    if text:
        return [l.strip() for l in text.replace("\r", "").split("\n") if l.strip()]
    if part_type == "transformer":
        lines = []
        try:
            type_name = element.Name
            if type_name and type_name != _equipment_name(element):
                lines.append(type_name)
        except Exception:
            pass
        return lines + ["TRANSFORMER"]
    return []


# ---------------------------------------------------------------- circuits

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
    override = _lookup(system, "SLD Cable")
    if override:
        return override
    return cable_from_revit_values(
        hots=_int_attr(system, "HotConductorsNumber"),
        neutrals=_int_attr(system, "NeutralConductorsNumber"),
        grounds=_int_attr(system, "GroundConductorsNumber"),
        wire_size_text=wire_size,
        build=_cable_build(system),
        runs=_int_attr(system, "RunsNumber", 1),
    )


def _circuit_type(system):
    """'spare', 'space' or '' (normal)."""
    try:
        from Autodesk.Revit.DB.Electrical import CircuitType
        ct = system.CircuitType
        if ct == CircuitType.Spare:
            return "spare"
        if ct == CircuitType.Space:
            return "space"
    except Exception:
        pass
    return ""


def _start_slot(system):
    try:
        slot = int(system.StartSlot)
        return slot if slot > 0 else None
    except Exception:
        return None


def extract(doc):
    """Collect EquipmentInfo/CircuitInfo lists (and phase counts) from the model."""
    equipment, ids, phases_of = [], set(), {}
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
                 .WhereElementIsNotElementType())
    for el in collector:
        level_name, elevation = _level(doc, el)
        part_type = _part_type(el)
        phases = _phases(doc, el)
        equipment.append(EquipmentInfo(
            id=el.UniqueId,
            name=_equipment_name(el),
            level_name=level_name,
            level_elevation=elevation,
            location=_location(el),
            form=_lookup(el, "SLD Form"),
            ways=_ways(el, phases),
            family_name=_family_name(el),
            part_type=part_type,
            symbol=_lookup(el, "SLD Symbol"),
            description=_description(el, part_type),
            incoming_cable=_lookup(el, "SLD Incoming Cable"),
        ))
        ids.add(el.UniqueId)
        phases_of[el.UniqueId] = phases

    circuits = []
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        if system.SystemType != ElectricalSystemType.PowerCircuit:
            continue
        source = system.BaseEquipment
        if source is None:
            continue  # circuit not connected to a panel
        kind = _circuit_type(system)
        if kind == "space":
            continue
        fed, branch_count = [], 0
        try:
            elements = list(system.Elements)
        except Exception:
            elements = []
        for el in elements:
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
            cable="" if kind == "spare" else _cable_text(system, wire_size),
            fed_equipment_ids=fed,
            branch_load_count=branch_count,
            start_slot=_start_slot(system),
            is_spare=(kind == "spare"),
            symbol=_lookup(system, "SLD Symbol"),
        ))
    return equipment, circuits, phases_of


# ---------------------------------------------------------------- drawing

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


def _xyz(x_mm, y_mm):
    return XYZ(x_mm / MM_PER_FOOT, y_mm / MM_PER_FOOT, 0.0)


def _set(element, bip_name, value):
    """Set a built-in parameter by name, ignoring ones this Revit lacks."""
    try:
        p = element.get_Parameter(getattr(BuiltInParameter, bip_name))
        if p is not None and not p.IsReadOnly:
            p.Set(value)
    except Exception:
        pass


class _TextTypes(object):
    """One 'SLD <size>mm Arial' text type per text size.

    Created on first use and brought back in line with style.py on every
    run: size, font, transparent background, small border offset.
    """

    def __init__(self, doc):
        self.doc = doc
        self.cache = {}
        self.existing = {}
        for t in FilteredElementCollector(doc).OfClass(TextNoteType):
            name_param = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if name_param is not None:
                self.existing[name_param.AsString()] = t
        self.default = doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType))

    def get(self, size_mm):
        key = round(size_mm, 2)
        if key in self.cache:
            return self.cache[key]
        name = "SLD %smm %s" % (("%.2f" % key).rstrip("0").rstrip("."), style.TEXT_FONT)
        text_type = self.existing.get(name)
        if text_type is None:
            text_type = self.default.Duplicate(name)
        _set(text_type, "TEXT_SIZE", size_mm / MM_PER_FOOT)
        _set(text_type, "TEXT_FONT", style.TEXT_FONT)
        _set(text_type, "TEXT_WIDTH_SCALE", 1.0)
        _set(text_type, "TEXT_BACKGROUND", 1)   # transparent
        _set(text_type, "TEXT_BOX_VISIBILITY", 0)
        _set(text_type, "LEADER_OFFSET_SHEET", style.TEXT_BORDER_OFFSET / MM_PER_FOOT)
        self.cache[key] = text_type.Id
        return text_type.Id


def _note_width(t):
    """Text note width (mm) wide enough that Revit never wraps the text:
    lines are already broken by the layout."""
    longest = max(line_length(line, t.size) for line in t.text.split("\n"))
    return longest * 1.2 + 2 * style.TEXT_BORDER_OFFSET + 2.0


_H_ALIGN = {CENTER: HorizontalTextAlignment.Center, RIGHT: HorizontalTextAlignment.Right}
_V_ALIGN = {TOP: VerticalTextAlignment.Top, MIDDLE: VerticalTextAlignment.Middle}


def render(doc, drawing, view_name=VIEW_NAME):
    """Create a new 1:1 drafting view and draw `drawing` into it.

    Must be called inside an open transaction. Returns the new view.
    """
    view = ViewDrafting.Create(doc, _drafting_view_type(doc).Id)
    view.Name = _unique_view_name(doc, view_name)
    view.Scale = 1  # 1:1 so layout millimetres == paper millimetres

    short = doc.Application.ShortCurveTolerance
    curves = CurveArray()
    for ln in drawing.lines:
        a, b = _xyz(ln.x1, ln.y1), _xyz(ln.x2, ln.y2)
        if a.DistanceTo(b) > short:
            curves.Append(Line.CreateBound(a, b))
    for arc in drawing.arcs:
        if arc.r * (arc.a1 - arc.a0) / MM_PER_FOOT > short:
            curves.Append(Arc.Create(_xyz(arc.cx, arc.cy), arc.r / MM_PER_FOOT,
                                     arc.a0, arc.a1, XYZ.BasisX, XYZ.BasisY))
    if not curves.IsEmpty:
        doc.Create.NewDetailCurveArray(view, curves)

    types = _TextTypes(doc)
    for t in drawing.texts:
        type_id = types.get(t.size)
        opts = TextNoteOptions(type_id)
        opts.HorizontalAlignment = _H_ALIGN.get(t.align, HorizontalTextAlignment.Left)
        opts.VerticalAlignment = _V_ALIGN.get(t.valign, VerticalTextAlignment.Bottom)
        if t.rotation:
            opts.Rotation = t.rotation
        min_w = TextNote.GetMinimumAllowedWidth(doc, type_id)
        max_w = TextNote.GetMaximumAllowedWidth(doc, type_id)
        width = min(max(_note_width(t) / MM_PER_FOOT, min_w), max_w)
        TextNote.Create(doc, view.Id, _xyz(t.x, t.y), width, t.text, opts)
    return view


def generate(doc, settings=None, numbering="slots"):
    """Build and draw the schematic. Returns (view or None, schematic)."""
    equipment, circuits, phases_of = extract(doc)
    schematic = build_schematic(equipment, circuits, phases_of, numbering)
    if not schematic.roots:
        return None, schematic

    layout = layout_schematic(schematic, settings or LayoutSettings())

    t = Transaction(doc, "Generate LV Schematic Diagram")
    t.Start()
    try:
        view = render(doc, layout.drawing)
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return view, schematic
