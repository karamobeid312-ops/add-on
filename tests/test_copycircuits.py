# -*- coding: utf-8 -*-
from copycircuits import settings
from copycircuits.plan import (
    ALREADY, NO_PANEL, NONE_FOUND, Circuit, Item, View, match, plan, target_view,
)
from copycircuits.report import LevelResult, Made, headline, made_note, wire_lines

TOL = 0.16      # about 50 mm in feet


def test_match_same_type_same_spot():
    source = [Item(1, "light", 0, 0), Item(2, "light", 10, 0), Item(3, "socket", 0, 0)]
    target = [Item(11, "light", 10.01, 0), Item(12, "light", 0, 0.02), Item(13, "socket", 0, 0)]
    assert match(source, target, TOL) == {1: 12, 2: 11, 3: 13}


def test_match_other_type_or_too_far_is_no_copy():
    source = [Item(1, "light", 0, 0), Item(2, "light", 5, 5)]
    target = [Item(11, "socket", 0, 0), Item(12, "light", 5.5, 5)]
    assert match(source, target, TOL) == {}


def test_match_is_one_to_one_nearest_first():
    source = [Item(1, "light", 0, 0), Item(2, "light", 0.1, 0)]
    target = [Item(11, "light", 0.09, 0)]
    assert match(source, target, TOL) == {2: 11}


def test_match_across_grid_cells():
    source = [Item(1, "light", 0.15, -0.01)]
    target = [Item(11, "light", 0.17, 0.01)]
    assert match(source, target, TOL) == {1: 11}


def circuit(key, elements, panel="P", panel_here=True, slot=1, kind="Power", number="1"):
    return Circuit(key, kind, elements, panel=panel, panel_here=panel_here, slot=slot,
                   panel_name="DB-1F", number=number)


def test_plan_panel_on_the_floor_uses_its_copy():
    jobs, skipped = plan([circuit(100, [1, 2])], {"P": "P2", 1: 11, 2: 12})
    assert skipped == []
    assert [(j.panel, j.elements, j.missing) for j in jobs] == [("P2", [11, 12], [])]


def test_plan_panel_elsewhere_feeds_the_copies_too():
    jobs, _ = plan([circuit(100, [1], panel="MDB", panel_here=False)], {1: 11})
    assert jobs[0].panel == "MDB"


def test_plan_no_panel_copy_skips():
    jobs, skipped = plan([circuit(100, [1])], {1: 11})
    assert jobs == [] and skipped[0].reason == NO_PANEL


def test_plan_semi_typical_leaves_out_missing_fixtures():
    jobs, _ = plan([circuit(100, [1, 2, 3])], {"P": "P2", 1: 11, 3: 13})
    assert jobs[0].elements == [11, 13]
    assert jobs[0].missing == [2]


def test_plan_nothing_copied_skips():
    _, skipped = plan([circuit(100, [1, 2])], {"P": "P2"})
    assert skipped[0].reason == NONE_FOUND and skipped[0].missing == [1, 2]


def test_plan_already_circuited_left_alone():
    jobs, skipped = plan([circuit(100, [1, 2]), circuit(101, [3])],
                         {"P": "P2", 1: 11, 2: 12, 3: 13},
                         circuited={(11, "Power"), (13, "Power")})
    assert jobs[0].elements == [12] and jobs[0].already == [11]
    assert skipped[0].reason == ALREADY


def test_plan_other_kind_of_circuit_is_not_in_the_way():
    jobs, _ = plan([circuit(100, [1], kind="Data")], {"P": "P2", 1: 11},
                   circuited={(11, "Power")})
    assert jobs[0].elements == [11]


def test_plan_in_slot_order():
    circuits = [circuit(100, [1], slot=5, number="5"), circuit(101, [2], slot=1, number="1"),
                circuit(102, [3], slot=3, number="3")]
    jobs, _ = plan(circuits, {"P": "P2", 1: 11, 2: 12, 3: 13})
    assert [j.circuit.number for j in jobs] == ["1", "3", "5"]


def test_plan_circuit_without_panel():
    jobs, _ = plan([circuit(100, [1], panel=None, panel_here=False)], {1: 11})
    assert jobs[0].panel is None


def test_label():
    assert circuit(1, [], number="7").label == "DB-1F / 7"
    assert Circuit(1, "Power", [], number="").label == "(no panel)"


def view(key, name, level, template=None, family_type=1, view_type="FloorPlan"):
    return View(key, name, view_type, level, template, family_type)


def test_target_view_named_like_the_source():
    source = view(1, "POWER - L1", "L1", template=9)
    candidates = [view(2, "LIGHTING - L2", "L2", template=9), view(3, "POWER - L2", "L2"),
                  view(4, "POWER - L3", "L3")]
    assert target_view(source, candidates, "L2").key == 3


def test_target_view_same_template_then_type():
    source = view(1, "Electrical", "L1", template=9)
    candidates = [view(2, "A", "L2", family_type=2), view(3, "B", "L2", template=9)]
    assert target_view(source, candidates, "L2").key == 3


def test_target_view_none_on_that_level():
    source = view(1, "POWER - L1", "L1")
    assert target_view(source, [view(2, "POWER - L1", "L1"),
                                view(3, "x", "L2", view_type="CeilingPlan")], "L2") is None


def test_settings():
    assert settings.valid("tolerance", "50") == 50.0
    assert settings.valid("tolerance", "0") is None
    assert settings.valid("tolerance", "2000") is None
    assert settings.valid("wires", "False") is False
    assert settings.coerce("wires", "maybe") is True


def test_report():
    jobs, _ = plan([circuit(100, [1, 2])], {"P": "P2", 1: 11})
    result = LevelResult("Level 2")
    assert headline(result) == "No circuits made on Level 2."
    result.made.append(Made(jobs[0], 500))
    result.made.append(Made(jobs[0], 501, panel_error="panel is full"))
    assert headline(result) == "2 circuits made on Level 2, 1 of them not on a panel."
    assert made_note(result.made[1]) == "not on a panel: panel is full; 1 element with no " \
                                        "copy left out"
    assert result.missing() == [2]
    result.wires.update(drawn=3, removed=2)
    result.wire_views["POWER - L3"] = 3
    assert wire_lines(result)[0] == "3 wires drawn, in POWER - L3 (3)."


def test_floor_name_swaps_the_floor_number():
    from copycircuits.plan import floor_name
    assert floor_name("DB-F4-01", "L4", "L3") == "DB-F3-01"
    assert floor_name("PP-4F-2", "Level 4", "Level 3") == "PP-3F-2"
    assert floor_name("DB-4-01", "L4", "L3") == "DB-3-01"
    assert floor_name("DB-F1-01", "L1", "L2") == "DB-F2-01"      # F1, not 01
    assert floor_name("DB-F09-01", "L9", "L10") == "DB-F10-01"
    assert floor_name("LP 04", "Level 04", "Level 03") == "LP 03"


def test_floor_name_none_when_unsure():
    from copycircuits.plan import floor_name
    assert floor_name("MDB", "L4", "L3") is None                # no floor number
    assert floor_name("DB-1-01", "L1", "L2") is None            # 1 or 01?
    assert floor_name("DB-F4-01", "GF", "L3") is None           # no number in the level
    assert floor_name("DB-F4-01", "L4", "L4") is None


def test_panel_rows():
    from copycircuits.plan import BY_NAME, BY_SPOT, NOT_FOUND, PanelMatch
    from copycircuits.report import panel_row, found_line
    assert panel_row(PanelMatch("DB-F4-01", BY_SPOT, "DB-F4-01(1)", circuits=12)) == \
        ["DB-F4-01", 12, "DB-F4-01(1)"]
    assert panel_row(PanelMatch("DB-F4-01", BY_NAME, "DB-F3-01", "DB-F3-01"))[2] == \
        "DB-F3-01 (by name)"
    row = panel_row(PanelMatch("DB-F4-01", NOT_FOUND, looked_for="DB-F3-01", nearest=2350.4))
    assert row[2] == "NOT FOUND: no panel named DB-F3-01, the nearest panel of its family " \
                     "type is 2350 mm away. Its circuits are not made."
    row = panel_row(PanelMatch("MDB", NOT_FOUND))
    assert "no floor number" in row[2] and "no panel of its family type" in row[2]
    result = LevelResult("L3")
    result.found, result.total = 310, 320
    assert found_line(result, "L4") == "310 of 320 elements on L4 found on L3 (same family " \
                                       "type, same spot)."


def test_wire_lines_say_why():
    result = LevelResult("L3")
    result.wires.update(no_copy=2, refused=1)
    result.wire_errors.append("The points are not in the view's plane")
    assert wire_lines(result) == [
        "2 wires not drawn: an element they connect has no copy here.",
        "1 wire not drawn: Revit refused them (The points are not in the view's plane).",
    ]


def test_match_same_height_above_the_floor():
    source = [Item(1, "fb", 0, 0, z=40.0), Item(2, "fb", 5, 0, z=40.0)]
    target = [Item(11, "fb", 0, 0, z=27.0), Item(12, "fb", 5, 0, z=40.0)]   # 12: still on L4
    assert match(source, target, TOL, dz=-13.0, z_tolerance=1.6) == {1: 11}


def test_match_falls_back_to_the_same_family():
    found = set()
    source = [Item(1, "fb-a", 0, 0, family_key="FB"), Item(2, "fb-a", 5, 0, family_key="FB")]
    target = [Item(11, "fb-a", 0, 0, family_key="FB"), Item(12, "fb-b", 5, 0, family_key="FB"),
              Item(13, "light", 5, 0, family_key="L")]
    assert match(source, target, TOL, by_family=found) == {1: 11, 2: 12}
    assert found == {2}


def test_match_prefers_the_same_type_over_the_family():
    source = [Item(1, "fb-a", 0, 0, family_key="FB")]
    target = [Item(11, "fb-b", 0, 0, family_key="FB"), Item(12, "fb-a", 0.1, 0, family_key="FB")]
    assert match(source, target, TOL) == {1: 12}


def test_found_line_by_family():
    from copycircuits.report import found_line
    result = LevelResult("L3")
    result.found, result.total, result.by_family = 300, 320, 12
    assert found_line(result, "L4") == "300 of 320 elements on L4 found on L3 (same family " \
                                       "type, same spot; 12 of them of another type of the " \
                                       "same family)."
