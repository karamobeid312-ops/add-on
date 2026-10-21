# -*- coding: utf-8 -*-
from circuitdesc.spares import (
    SECTION_100MA as S1, SECTION_30MA as S2, BoardPlan, Item, rcd_text, spares_needed, ways_for,
)


def board(items, spares=(), spaces=(), max_slots=42, rcds=None):
    return BoardPlan(None, u"DB", items, spares, spaces, max_slots, 3, rcds)


def singles(sections, load=1000.0):
    """Single-pole circuits in slots 1, 2, 3... of the given sections."""
    return [Item(i + 1, i + 1, 1, s, load) for i, s in enumerate(sections)]


def test_spares_ten_percent_rounded_up():
    assert [spares_needed(n) for n in (0, 1, 10, 11, 29)] == [0, 1, 1, 2, 3]


def test_standard_way_sizes():
    assert ways_for(32) == 12 and ways_for(36) == 12 and ways_for(37) == 16
    assert ways_for(3) == 4


def test_rcd_from_the_section_load():
    assert rcd_text(10000, S1) == u"RCCB 25A 4P 100mA"          # 14.4 A
    assert rcd_text(20000, S2) == u"RCCB 40A 4P 30mA"           # 28.9 A
    assert rcd_text(40000, S2) == u"RCCB 63A 4P 30mA"           # 57.7 A
    assert rcd_text(9000, S1, per_way=1) == u"RCCB 40A 2P 100mA"  # 39.1 A single phase
    assert rcd_text(500000, S2) == u"RCCB 125A 4P 30mA"         # biggest there is


def test_lighting_and_fcu_first_then_power_on_a_new_way():
    # slots 1..7: power, light, power, light, light, power, fcu
    plan = board(singles([S2, S1, S2, S1, S1, S2, S1]))
    t = plan.targets
    assert [t[k] for k in (2, 4, 5, 7)] == [1, 2, 3, 4]         # section 1 in order
    assert plan.spare_slots[S1] == [5]                          # 1 spare for 4 circuits
    assert [t[k] for k in (1, 3, 6)] == [7, 8, 9]               # section 2 on a new way
    assert plan.spare_slots[S2] == [10]
    assert plan.ways == 4 and plan.slots == 12
    assert plan.spaces == [6, 11, 12]
    assert plan.changed and len(plan.moved) == 7


def test_section_rcds_and_text():
    plan = board(singles([S1] * 3 + [S2] * 3, load=5000.0))
    assert plan.rcds == {S1: u"RCCB 25A 4P 100mA", S2: u"RCCB 25A 4P 30mA"}
    assert plan.text() == (u"4 ways (was 14), RCCB 25A 4P 100mA: 3 circuits + 1 spare, "
                           u"RCCB 25A 4P 30mA: 3 circuits + 1 spare, 4 spaces, 3 circuits moved")


def test_three_pole_circuit_starts_on_a_way():
    items = [Item(1, 1, 1, S2), Item(2, 2, 3, S2), Item(3, 5, 1, S2)]
    plan = board(items)
    assert plan.targets == {1: 1, 2: 4, 3: 2}
    assert plan.spare_slots[S2] == [3]


def test_only_power():
    plan = board(singles([S2] * 29))
    assert S1 not in plan.rcds
    assert plan.spare_slots[S2] == [30, 31, 32] and plan.ways == 12
    assert plan.spaces == [33, 34, 35, 36] and not plan.moved


def test_nothing_to_do_twice():
    first = board(singles([S2, S1, S2, S1]))
    items = [Item(i.key, first.targets[i.key], 1, i.section, i.load_va) for i in first.items]
    again = BoardPlan(None, u"DB", items, first.new_spares, first.spaces, first.slots, 3,
                      first.rcds)
    assert not again.changed


def test_empty_board_left_alone():
    assert not board([]).changed
