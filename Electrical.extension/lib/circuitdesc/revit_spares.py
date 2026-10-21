# -*- coding: utf-8 -*-
"""A board laid out in its panel schedule: circuits moved into their RCD
section, spares and spaces added, its ways (Max #1 Pole Breakers,
No_Of_Ways) and RCDs (Section1/2_Protection) set."""
from Autodesk.Revit.DB import BuiltInParameter, FilteredElementCollector, StorageType
from Autodesk.Revit.DB.Electrical import ElectricalSystem

from circuitdesc import revit_desc
from circuitdesc.spares import (
    CIRCUIT, SECTION_100MA, SECTION_30MA, SPACE, SPARE, BoardPlan, Item,
)

P_WAYS = "No_Of_Ways"
P_SECTION = "Section%d_Protection"


def _kind(system):
    try:
        from Autodesk.Revit.DB.Electrical import CircuitType
        return {CircuitType.Spare: SPARE, CircuitType.Space: SPACE}.get(
            system.CircuitType, CIRCUIT)
    except Exception:
        return CIRCUIT


def _per_way(board):
    """Slots in a way: 3 on a three phase board, 1 on a single phase one."""
    try:
        from Autodesk.Revit.DB.Electrical import ElectricalPhase
        dist = board.Document.GetElement(board.get_Parameter(
            BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM).AsElementId())
        if dist is not None and dist.ElectricalPhase == ElectricalPhase.SinglePhase:
            return 1
    except Exception:
        pass
    return 3


def _max_slots(board):
    try:
        return board.get_Parameter(BuiltInParameter.RBS_ELEC_MAX_POLE_BREAKERS).AsInteger()
    except Exception:
        return 0


def board_systems(board):
    """Every circuit, spare and space of the board."""
    out = []
    for system in FilteredElementCollector(board.Document).OfClass(ElectricalSystem):
        try:
            if system.BaseEquipment is not None and \
                    revit_desc.id_int(system.BaseEquipment.Id) == revit_desc.id_int(board.Id):
                out.append(system)
        except Exception:
            continue
    return out


def plan(board, info):
    """BoardPlan of a board from what is in its slots now. `info` maps a
    circuit id to (section, load in VA); circuits not in it go to the
    30 mA section."""
    items, spares, spaces = [], [], []
    for system in board_systems(board):
        try:
            start, poles = system.StartSlot, max(system.PolesNumber, 1)
        except Exception:
            continue
        kind = _kind(system)
        if kind == SPARE:
            spares.extend(range(start, start + poles))
        elif kind == SPACE:
            spaces.extend(range(start, start + poles))
        else:
            key = revit_desc.id_int(system.Id)
            section, load = info.get(key, (SECTION_30MA, revit_desc.circuit_watts(system)))
            items.append(Item(key, start, poles, section, load, system.CircuitNumber))
    rcds = dict((s, revit_desc.text_of(board.LookupParameter(P_SECTION % s)))
                for s in (SECTION_100MA, SECTION_30MA))
    return BoardPlan(board, revit_desc.panel_name(board), items, spares, spaces,
                     _max_slots(board), _per_way(board), rcds)


# ---------------------------------------------------------------- schedule

def schedule_view(board):
    """The board's panel schedule, made when it has none."""
    from Autodesk.Revit.DB.Electrical import PanelScheduleView
    doc = board.Document
    for view in FilteredElementCollector(doc).OfClass(PanelScheduleView):
        try:
            if not view.IsTemplate and \
                    revit_desc.id_int(view.GetPanel()) == revit_desc.id_int(board.Id):
                return view
        except Exception:
            continue
    return PanelScheduleView.CreateInstanceView(doc, board.Id)


def _cell(view, slot):
    """(row, column) of a slot in the panel schedule."""
    try:
        found = view.GetCellsBySlotNumber(slot)              # IronPython: out values
    except TypeError:
        found = view.GetCellsBySlotNumber(slot, None, None)  # pythonnet
    rows, cols = [list(x) for x in found if x is not None and not isinstance(x, bool)][-2:]
    return rows[0], cols[0]


def _set_ways(board, ways, slots):
    """Max #1 Pole Breakers and No_Of_Ways: a way is one slot (R1 or Y1)."""
    p = board.get_Parameter(BuiltInParameter.RBS_ELEC_MAX_POLE_BREAKERS)
    if p is not None and not p.IsReadOnly and p.AsInteger() != slots:
        p.Set(slots)
    p = board.LookupParameter(P_WAYS)
    if p is None or p.IsReadOnly:
        return
    if p.StorageType == StorageType.String:
        p.Set(u"%d" % ways)
    elif p.StorageType == StorageType.Integer:
        p.Set(ways)
    elif p.StorageType == StorageType.Double:
        p.Set(float(ways))


def _set_text(element, name, text):
    p = element.LookupParameter(name)
    if p is not None and not p.IsReadOnly and p.StorageType == StorageType.String:
        p.Set(text)


def _set_max_slots(board, slots):
    p = board.get_Parameter(BuiltInParameter.RBS_ELEC_MAX_POLE_BREAKERS)
    if p is not None and not p.IsReadOnly and p.AsInteger() != slots:
        p.Set(slots)
    board.Document.Regenerate()


def apply(board_plan, spare_amps):
    """Lay the board out as planned: spares and spaces taken out, circuits
    moved to their section (through free slots past the board), the ways
    set, spares (`spare_amps` {section: A}) and spaces added, and the RCD
    of each section written to Section1/2_Protection."""
    board, doc = board_plan.ref, board_plan.ref.Document
    view = schedule_view(board)
    for system in board_systems(board):
        kind = _kind(system)
        if kind in (SPARE, SPACE):
            row, col = _cell(view, system.StartSlot)
            if kind == SPARE:
                view.RemoveSpare(row, col)
            else:
                view.RemoveSpace(row, col)
    doc.Regenerate()

    moved = board_plan.moved
    per_way = board_plan.per_way
    top = max(board_plan.old_slots, board_plan.slots)
    top += (per_way - top % per_way) % per_way
    _set_max_slots(board, top + len(moved) * per_way * max([1] + [i.poles for i in moved]))
    staged = {}
    stage = top + 1
    for item in moved:                  # out of the way first...
        row, col = _cell(view, item.slot)
        to_row, to_col = _cell(view, stage)
        view.MoveSlotTo(row, col, to_row, to_col)
        staged[item.key] = stage
        stage += per_way * max(1, int((item.poles + per_way - 1) / per_way))
    doc.Regenerate()
    for item in moved:                  # ...then into their section
        row, col = _cell(view, staged[item.key])
        to_row, to_col = _cell(view, board_plan.targets[item.key])
        view.MoveSlotTo(row, col, to_row, to_col)
    doc.Regenerate()
    _set_max_slots(board, board_plan.slots)
    _set_ways(board, board_plan.ways, board_plan.slots)

    for section, slots in board_plan.spare_slots.items():
        for slot in slots:
            row, col = _cell(view, slot)
            view.AddSpare(row, col)
            try:
                view.GetCircuitByCell(row, col).get_Parameter(
                    BuiltInParameter.RBS_ELEC_CIRCUIT_RATING_PARAM).Set(spare_amps[section])
            except Exception:
                pass
    for slot in board_plan.spaces:
        row, col = _cell(view, slot)
        if view.GetCircuitByCell(row, col) is None:
            view.AddSpace(row, col)
    for section, text in board_plan.rcds.items():
        _set_text(board, P_SECTION % section, text)
