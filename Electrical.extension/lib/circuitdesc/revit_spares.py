# -*- coding: utf-8 -*-
"""Spares and spaces written into a board's panel schedule, and its ways
(Max #1 Pole Breakers, No_Of_Ways) set."""
from Autodesk.Revit.DB import BuiltInParameter, FilteredElementCollector, StorageType
from Autodesk.Revit.DB.Electrical import ElectricalSystem

from circuitdesc import revit_desc
from circuitdesc.spares import CIRCUIT, SPACE, SPARE, BoardPlan

P_WAYS = "No_Of_Ways"
SPARE_RATING = {True: 16.0, False: 20.0}        # all lighting: 16 A, else 20 A


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


def plan(board):
    """BoardPlan of a board from what is in its slots now."""
    taken, circuits = {}, 0
    for system in board_systems(board):
        try:
            start, poles = system.StartSlot, max(system.PolesNumber, 1)
        except Exception:
            continue
        kind = _kind(system)
        if kind == CIRCUIT:
            circuits += 1
        for slot in range(start, start + poles):
            taken[slot] = kind
    return BoardPlan(board, revit_desc.panel_name(board), taken, circuits,
                     _max_slots(board), _per_way(board))


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


def apply(board_plan, lighting):
    """Remove the spaces past the new ways, set the ways, add the spares
    (16 A on lighting boards, 20 A else) and the spaces."""
    board, doc = board_plan.ref, board_plan.ref.Document
    view = schedule_view(board)
    for slot in board_plan.removed:
        row, col = _cell(view, slot)
        system = view.GetCircuitByCell(row, col)
        if system is not None and _kind(system) == SPACE:
            view.RemoveSpace(row, col)
        elif system is not None and _kind(system) == SPARE:
            view.RemoveSpare(row, col)
    doc.Regenerate()
    _set_ways(board, board_plan.ways, board_plan.slots)
    doc.Regenerate()
    for slot in board_plan.spaces_to_spares:
        row, col = _cell(view, slot)
        view.RemoveSpace(row, col)
    for slot in board_plan.new_spares:
        row, col = _cell(view, slot)
        view.AddSpare(row, col)
        system = view.GetCircuitByCell(row, col)
        try:
            system.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_RATING_PARAM).Set(
                SPARE_RATING[bool(lighting)])
        except Exception:
            pass
    for slot in board_plan.new_spaces:
        row, col = _cell(view, slot)
        if view.GetCircuitByCell(row, col) is None:
            view.AddSpace(row, col)
