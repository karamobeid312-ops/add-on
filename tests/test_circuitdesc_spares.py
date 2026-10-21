# -*- coding: utf-8 -*-
from circuitdesc.spares import CIRCUIT, SPACE, SPARE, BoardPlan, spares_needed, ways_for


def board(circuit_slots, extra=None, circuits=None, max_slots=42):
    taken = dict((s, CIRCUIT) for s in circuit_slots)
    taken.update(extra or {})
    n = len(circuit_slots) if circuits is None else circuits
    return BoardPlan(None, u"DB", taken, n, max_slots)


def test_spares_ten_percent_rounded_up():
    assert spares_needed(0) == 0
    assert spares_needed(1) == 1
    assert spares_needed(10) == 1
    assert spares_needed(11) == 2
    assert spares_needed(29) == 3


def test_standard_way_sizes():
    assert ways_for(32) == 12            # 11 ways -> 12
    assert ways_for(36) == 12
    assert ways_for(37) == 16
    assert ways_for(3) == 4
    assert ways_for(130) == 44           # bigger than any standard board


def test_the_pdb_board():
    plan = board(range(1, 30))           # R1..R10, Y1..Y10, B1..B9 = 29 slots
    assert plan.new_spares == [30, 31, 32]
    assert plan.ways == 12 and plan.slots == 36
    assert plan.new_spaces == [33, 34, 35, 36]
    assert plan.spaces == 4 and plan.changed
    assert plan.text() == u"12 ways (was 14): 29 circuits, 3 spares (+3), 4 spaces"


def test_spares_fill_gaps_first():
    plan = board([1, 2, 4, 5])
    assert plan.new_spares == [3]
    assert plan.ways == 4 and plan.new_spaces == list(range(6, 13))


def test_existing_spares_count_and_spaces_become_spares():
    plan = board(range(1, 12), {12: SPARE, 13: SPACE})
    assert plan.spares == 2 and plan.new_spares == [13]
    assert plan.spaces_to_spares == [13]


def test_spaces_past_the_ways_are_removed():
    plan = board([1, 2, 3], {40: SPACE, 41: SPACE})
    assert plan.ways == 4 and plan.removed == [40, 41]


def test_multi_pole_circuit_counts_once():
    plan = board([1, 2, 3, 4], circuits=2)          # a 3-pole and a 1-pole circuit
    assert plan.spares == 1 and plan.new_spares == [5]


def test_nothing_to_do_twice():
    first = board(range(1, 30))
    taken = dict((s, CIRCUIT) for s in range(1, 30))
    taken.update((s, SPARE) for s in first.new_spares)
    taken.update((s, SPACE) for s in first.new_spaces)
    again = BoardPlan(None, u"DB", taken, 29, first.slots)
    assert not again.changed


def test_empty_board_left_alone():
    assert not board([]).changed
