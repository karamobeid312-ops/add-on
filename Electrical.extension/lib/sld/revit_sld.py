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
    SLD Frame           incoming breaker frame in A, e.g. "250" (default: the
                        smallest standard frame for its MCB Rating)
    SLD Fault Level     e.g. "35kA" (default: the panel's Short Circuit Rating)
  Electrical Circuits
    SLD Cable           cable text printed exactly as typed
    SLD Symbol          ISOLATOR / DB / SPARE / PFC (force the way symbol)
    SLD Frame           breaker frame in A, e.g. "250"

Office panel family parameters are read first:

  SC_Rating_kA                  fault level in the board text (10kA FOR 1 SEC)
  Incomer_Rating_A / _Type      incoming breaker (100A,3P + MCCB -> 100AT/100AF
                                MCCB; a switch such as MCS prints 100A / MCS)
  Upstream_Protection_Rating_A  the breaker on the way feeding the panel, e.g.
  / Upstream_Protection_Type    40AT/100AF + MCCB (else the circuit Rating)
  Feeder_Length_m               length of the cable feeding the panel (when
                                VD Length is empty)
  No_Of_Ways                    number of ways in the board text

Breakers are printed as trip / frame / device (40AT / 100AF / MCCB), the
frame being the smallest standard size for the trip unless typed. The board
text starts with the busbar (panel Mains), the system (3PH+N+E) and the fault
level.

CL / DL beside a DB and the board load table are the panel's Total Connected
Apparent Power, Total Demand Apparent Power and Total Demand Factor (shown in
kW as VA / 1000). A final circuit counts its load in both.

The cable comes from the circuit's Wire Size; when Revit has none, from the
VD Cable typed for the Voltage Drop tool. Lengths and the cumulative V.D %
come from the Voltage Drop tool with its VD Settings, as in its report.
"""
from __future__ import division


from Autodesk.Revit.DB import (
    Arc, BuiltInCategory, BuiltInParameter, Color, CurveArray, ElementId,
    GraphicsStyleType,
    ElementTypeGroup, FilteredElementCollector, HorizontalTextAlignment, Line,
    StorageType, TextNote, TextNoteOptions, TextNoteType, Transaction,
    VerticalTextAlignment, View, ViewDrafting, ViewFamily, ViewFamilyType, XYZ,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from sld import style
from sld.cables import (cable_from_revit_values, conductor_code, construction,
                        format_cable, insulation_code)
from sld.geometry import CENTER, MIDDLE, RIGHT, TOP, line_length
from sld.layout import LayoutSettings, layout_schematic
from sld.model import CircuitInfo, EquipmentInfo, add_fed_by, build_schematic, fed_by_links

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


def _distribution(doc, element):
    try:
        dist_id = element.get_Parameter(
            BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM).AsElementId()
        return doc.GetElement(dist_id)
    except Exception:
        return None


def _phases(doc, element):
    try:
        from Autodesk.Revit.DB.Electrical import ElectricalPhase
        dist = _distribution(doc, element)
        if dist is not None and dist.ElectricalPhase == ElectricalPhase.SinglePhase:
            return 1
    except Exception:
        pass
    return 3


def _has_neutral(doc, element, phases):
    """False only for a three-wire three-phase (or two-wire) system."""
    try:
        wires = int(_distribution(doc, element).NumWires)
        return wires > phases
    except Exception:
        return True


def _amps(element, bip_name):
    """A current parameter in amperes, or None."""
    try:
        p = element.get_Parameter(getattr(BuiltInParameter, bip_name))
        if p is None or not p.HasValue:
            return None
        if p.StorageType == StorageType.Double:
            value = p.AsDouble()
            return value if value > 0 else None
        return p.AsValueString() or p.AsString() or None
    except Exception:
        return None


# Office panel family parameters (DM_EL_EQ_Panel...), used first.
P_SC_RATING = "SC_Rating_kA"                          # 10kA
P_INCOMER = "Incomer_Rating_A"                        # 100A,3P
P_INCOMER_TYPE = "Incomer_Type"                       # MCCB / MCS / ACB
P_UPSTREAM = ("Upstream_Protection_Rating_A",         # 40AT/100AF
              "Upstream_Protection_Type")             # MCCB
P_WAYS = "No_Of_Ways"
P_SPARES = "SLD Spares"                              # spare ways drawn, e.g. 3
P_SPARE_RATING = "SLD Spare Rating"                   # 63AT/100AF MCCB
P_BREAKER_TYPE = "SLD Breaker Type"                   # on circuits: MCB / MCCB...
P_FED_BY = "Fed_By"                     # board feeding a panel not connected in this model
# Revit panel loads, by name (newer Revit), else the built-in totals.
P_CONNECTED = "Total Connected Apparent Power"
P_DEMAND = "Total Demand Apparent Power"
P_DEMAND_FACTOR = "Total Demand Factor"
INTERNAL_POWER = 0.3048 ** 2     # Revit power unit in W (VA)


def _incomer_rating(element):
    """Incoming breaker: Incomer_Rating_A, else MCB Rating, else Mains."""
    return (_lookup(element, P_INCOMER) or _amps(element, "RBS_ELEC_PANEL_MCB_RATING_PARAM") or
            _amps(element, "RBS_ELEC_MAINS"))


def _fault_level(element):
    typed = _lookup(element, "SLD Fault Level") or _lookup(element, P_SC_RATING)
    if typed:
        return typed
    bip = getattr(BuiltInParameter, "RBS_ELEC_SHORT_CIRCUIT_RATING", None)
    return _param_text(element, bip) if bip is not None else ""


def _upstream(element):
    return " ".join(t for t in (_lookup(element, n) for n in P_UPSTREAM) if t)


def _double(element, name=None, bip_name=None):
    """A Number parameter by name (or built-in), None when missing or 0."""
    try:
        if name is not None:
            p = element.LookupParameter(name)
        else:
            p = element.get_Parameter(getattr(BuiltInParameter, bip_name))
        if p is None or not p.HasValue or p.StorageType != StorageType.Double:
            return None
        value = p.AsDouble()
        return value if value > 0 else None
    except Exception:
        return None


def _kw(element, name, bip_name):
    """A panel load in kW as Revit shows it (VA / 1000)."""
    value = _double(element, name) or _double(element, bip_name=bip_name)
    return value * INTERNAL_POWER / 1000.0 if value else None


def _panel_loads(element):
    """(connected kW, demand kW, demand factor) of a panel: Total Connected /
    Total Demand Apparent Power and Total Demand Factor."""
    connected = _kw(element, P_CONNECTED, "RBS_ELEC_PANEL_TOTALLOAD_PARAM")
    demand = _kw(element, P_DEMAND, "RBS_ELEC_PANEL_TOTALESTLOAD_PARAM")
    factor = _double(element, P_DEMAND_FACTOR)
    return connected, demand, factor


def _ways(element, phases):
    declared = _lookup(element, "SLD Ways")
    if declared:
        return declared
    typed = _lookup(element, P_WAYS)
    if typed and typed.replace(".", "").strip("0"):
        return typed.split(".")[0]
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


def _wire_size(system):
    text = _param_text(system, BuiltInParameter.RBS_ELEC_CIRCUIT_WIRE_SIZE_PARAM)
    if not text:
        try:
            text = (system.WireSizeString or "").strip()
        except Exception:
            text = ""
    return text


def _vd_cable_text(cable, system):
    """Cable text from the VD Cable the Voltage Drop tool read for this way
    (or typed on the circuit), e.g. 4Cx10mm² Cu/XLPE/SWA/PVC, or ''."""
    if cable is None:
        try:
            from vdrop import parse
            cable = parse.cable(_lookup(system, "VD Cable"))
        except Exception:
            cable = None
    if cable is None or not cable.size:
        return ""
    build = "Cu/%s" % cable.insulation if cable.insulation else construction()
    return format_cable(cable.cores or 4, cable.size, build=build, runs=cable.runs or 1)


def _typed_cable_text(elements):
    """VD Cable, else Feeder_Size + Feeder_Type, typed on the fed panel or
    the circuit (what the editor saves), in the office format; '' when none
    can be read."""
    from sld import cablespec
    for element in elements:
        if element is None:
            continue
        text = _lookup(element, "VD Cable")
        spec = cablespec.parse(text) if text else None
        spec = spec or cablespec.from_feeder(_lookup(element, "Feeder_Size"),
                                             _lookup(element, "Feeder_Type"))
        if spec is not None:
            return spec.text()
    return ""


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


def _vd_results(doc, live=None):
    """Lengths and voltage drops as the Voltage Drop tool works them out.

    Returns ({panel or circuit id: (length m, cumulative V.D %)}, {circuit
    id: load kW}, {panel or circuit id: cable}, warning or None). A panel's
    row is its incoming cable, so its id gives the V.D (and the VD Cable)
    of the way feeding it. `live` (a dict) receives the VD feeders and
    settings, for the editor to recalculate as cables are changed.
    """
    try:
        from vdrop import calc, revit_vd
        from vdrop import settings as vd_settings
        values = vd_settings.load()
        model = revit_vd.collect(doc, values)
        calc_settings = vd_settings.calc_settings(values)
        result = calc.calculate(model.feeders, calc_settings)
        if live is not None:
            live.update(feeders=model.feeders, settings=calc_settings,
                        kinds=dict((k, e.kind) for k, e in model.equipment.items()))
    except Exception as error:
        return {}, {}, {}, u"Lengths and voltage drops not read: %s" % error

    vd, cables = {}, {}
    for row in result.rows():
        f = row.feeder
        cables[f.id] = f.cable
        vd[f.id] = (f.length, row.total_percent)

    circuit_kw = {}
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        try:
            circuit_kw[system.UniqueId] = revit_vd._circuit_values(system)[1]
        except Exception:
            pass
    return vd, circuit_kw, cables, None


def extract(doc, live=None):
    """Collect EquipmentInfo/CircuitInfo lists (and phase counts) from the
    model, and warnings about what could not be read. `live`: see
    _vd_results."""
    vd, circuit_kw, vd_cables, warning = _vd_results(doc, live)
    warnings = [warning] if warning else []
    equipment, ids, phases_of, panels = [], set(), {}, {}
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
                 .WhereElementIsNotElementType())
    for el in collector:
        level_name, elevation = _level(doc, el)
        part_type = _part_type(el)
        phases = _phases(doc, el)
        connected, demand, factor = _panel_loads(el)
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
            connected_kw=connected,
            demand_kw=demand,
            demand_factor=factor,
            mains_rating=_amps(el, "RBS_ELEC_MAINS"),
            incomer_rating=_incomer_rating(el),
            incomer_frame=_lookup(el, "SLD Frame"),
            incomer_device=_lookup(el, P_INCOMER_TYPE),
            upstream_protection=_upstream(el),
            phases=phases,
            neutral=_has_neutral(doc, el, phases),
            fault_level=_fault_level(el),
            spares=_lookup(el, P_SPARES) or None,
            spare_rating=_lookup(el, P_SPARE_RATING),
            fed_by=_lookup(el, P_FED_BY),
        ))
        ids.add(el.UniqueId)
        panels[el.UniqueId] = el
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
        wire_size = _wire_size(system)
        # a circuit to a panel: the panel's row is its cable
        row_id = next((i for i in fed if i in vd), system.UniqueId)
        length, vd_percent = vd.get(row_id, (None, None))
        # SLD Cable, else a typed VD Cable (the editor saves both), else Revit's wire size
        cable = "" if kind == "spare" else (
            _lookup(system, "SLD Cable") or
            _typed_cable_text([panels.get(i) for i in fed] + [system]) or
            _cable_text(system, wire_size) or
            _vd_cable_text(vd_cables.get(row_id), system))
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
            cable=cable,
            fed_equipment_ids=fed,
            branch_load_count=branch_count,
            start_slot=_start_slot(system),
            is_spare=(kind == "spare"),
            symbol=_lookup(system, "SLD Symbol"),
            connected_kw=None if kind == "spare" else circuit_kw.get(system.UniqueId),
            length_m=length,
            vd_percent=vd_percent,
            frame=_lookup(system, "SLD Frame"),
            device=_lookup(system, P_BREAKER_TYPE),
        ))
    equipment, circuits = _fed_by(equipment, circuits, panels, vd, vd_cables)
    return equipment, circuits, phases_of, warnings


def _fed_by(equipment, circuits, panels, vd, vd_cables):
    """Ways to the panels no circuit feeds, from the board in their Fed_By
    (a stand-in when that board is in another model)."""
    connected = set(f for c in circuits for f in c.fed_equipment_ids if f != c.source_id)
    links = fed_by_links(dict((e.id, e) for e in equipment), connected)
    details = {}
    for pid in links:
        length, vd_percent = vd.get(pid, (None, None))
        cable = (_lookup(panels[pid], "SLD Incoming Cable") or
                 _typed_cable_text([panels[pid]]) or
                 _vd_cable_text(vd_cables.get(pid), panels[pid]))
        details[pid] = dict(cable=cable, length_m=length, vd_percent=vd_percent)
    return add_fed_by(equipment, circuits, links, details)


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


def line_style(doc, name, colour):
    """The line style (a Lines subcategory) called `name`, made with
    `colour` (r, g, b) the first time."""
    categories = doc.Settings.Categories
    lines = categories.get_Item(BuiltInCategory.OST_Lines)
    if lines.SubCategories.Contains(name):
        sub = lines.SubCategories.get_Item(name)
    else:
        sub = categories.NewSubcategory(lines, name)
        sub.LineColor = Color(colour[0], colour[1], colour[2])
    return sub.GetGraphicsStyle(GraphicsStyleType.Projection)


def render(doc, drawing, view_name=VIEW_NAME):
    """Create a new 1:1 drafting view and draw `drawing` into it.

    Must be called inside an open transaction. Returns the new view.
    """
    view = ViewDrafting.Create(doc, _drafting_view_type(doc).Id)
    view.Name = _unique_view_name(doc, view_name)
    view.Scale = 1  # 1:1 so layout millimetres == paper millimetres

    short = doc.Application.ShortCurveTolerance
    by_style = {}
    for ln in drawing.lines:
        a, b = _xyz(ln.x1, ln.y1), _xyz(ln.x2, ln.y2)
        if a.DistanceTo(b) > short:
            by_style.setdefault(getattr(ln, "style", None), CurveArray()).Append(
                Line.CreateBound(a, b))
    for arc in drawing.arcs:
        if arc.r * (arc.a1 - arc.a0) / MM_PER_FOOT > short:
            by_style.setdefault(getattr(arc, "style", None), CurveArray()).Append(
                Arc.Create(_xyz(arc.cx, arc.cy), arc.r / MM_PER_FOOT,
                           arc.a0, arc.a1, XYZ.BasisX, XYZ.BasisY))
    for name, curves in by_style.items():
        if curves.IsEmpty:
            continue
        made = doc.Create.NewDetailCurveArray(view, curves)
        if name is None:
            continue
        graphics = line_style(doc, name, getattr(drawing, "styles", {}).get(name, (0, 0, 0)))
        for curve in made:
            curve.LineStyle = graphics

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
    equipment, circuits, phases_of, warnings = extract(doc)
    schematic = build_schematic(equipment, circuits, phases_of, numbering)
    schematic.warnings = warnings + schematic.warnings
    if schematic.is_empty():
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
