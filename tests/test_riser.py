# -*- coding: utf-8 -*-
import sample_tower
from sld.layout import layout_schematic
from sld.model import build_schematic
from sld import riser as rs
from test_layout import overlaps


def tower(connected=False, floors=6, specs=None):
    s = build_schematic(*sample_tower.build(connected=connected, tower_floors=floors))
    warnings = rs.apply_risers(s, sample_tower.risers(floors) if specs is None else specs)
    return s, warnings


def test_unconnected_tower_boards_go_on_a_new_mdb_way():
    s, warnings = tower()
    assert warnings == []
    r = s.risers[0]
    assert [t.board.name for t in r.taps] == ["SMDB-T-%d" % f for f in range(1, 7)]
    assert [t.is_typical for t in r.taps] == [False] + [True] * 5
    mdb = s.roots[0]
    assert mdb.name == "MDB-01" and mdb.ways[-1] is r.way
    assert r.way.label == "2" and r.way.breaker_lines() == ["1000AT", "1000AF", "ACB"]
    assert r.way.rating_lines() == []
    names = [b.name for b in s.boards()]
    assert "SMDB-T-1" in names and "SMDB-T-2" not in names      # typicals drawn as boxes
    assert r.label() == "1000A TPN+E COPPER BUS BAR RISER-1   432.00KW   50KA"
    assert r.way.loads() == (432.0, 336.0)
    assert r.taps[0].rating_text() == "160A"                       # board's incomer
    assert r.taps[0].cable_lines()[-1] == "L:12m"                  # Feeder_* on the board


def test_connected_tower_boards_share_one_way():
    s, warnings = tower(connected=True)
    assert warnings == []
    mdb = s.roots[0]
    r = s.risers[0]
    # SMDB-G, then the riser on the first way that fed a tower board
    assert [w.label for w in mdb.ways] == ["1", "2"] and mdb.ways[1] is r.way
    assert r.way.breaker_lines() == ["1000AT", "1000AF", "ACB"]
    assert all(t.board.parent is None for t in r.taps)
    assert not [b for b in mdb.children if b.name.startswith("SMDB-T")]


def test_typical_of_a_board_not_on_the_riser_is_drawn_in_full():
    specs = sample_tower.risers(3)
    specs[0]["taps"][2]["typical"] = "SMDB-X"
    s, warnings = tower(floors=3, specs=specs)
    assert len(warnings) == 1 and "SMDB-X" in warnings[0]
    assert [t.is_typical for t in s.risers[0].taps] == [False, True, False]


def test_missing_source_is_a_warning():
    specs = sample_tower.risers(2)
    specs[0]["source"] = "MDB-99"
    s, warnings = tower(floors=2, specs=specs)
    assert s.risers == [] and "MDB-99" in warnings[0]


def test_riser_boards_drawn_on_their_own_floors():
    for connected in (False, True):
        s, _ = tower(connected=connected)
        lay = layout_schematic(s)
        problems = overlaps(lay.drawing)
        assert not problems, problems[:10]
        mdb = lay.geoms["mdb"]
        block = mdb.riser_blocks[0]
        assert block.bottom > mdb.top
        labels = [label for label, _ in lay.bands]
        assert labels[:2] == ["SUBSTATION", "GROUND FLOOR"]
        floor_y = dict(lay.bands)
        names = ["1ST FLOOR", "2ND FLOOR", "3RD FLOOR", "4TH FLOOR", "5TH FLOOR", "6TH FLOOR"]
        assert all(n in floor_y for n in names)
        ys = block.tap_ys()
        assert ys == sorted(ys)
        # each tap-off between its floor line and the next one up
        ordered = sorted(floor_y.values())
        for (tap, g, _), y in zip(block.items, ys):
            fy = floor_y[tap.board.equipment.level_name.upper()]
            above = [v for v in ordered if v > fy]
            assert fy < y and (not above or y < above[0]), tap.board.name
        master = lay.geoms["t1"]
        assert master.left > block.x
        assert block.bottom < master.bottom < block.top


def test_two_risers_side_by_side_without_crossing():
    s = build_schematic(*sample_tower.build(connected=True, tower_floors=8))
    specs = [dict(name="RISER-1", rating="1000", fault="50", source="MDB-01",
                  taps=[dict(board="SMDB-T-%d" % f, typical="" if f == 1 else "SMDB-T-1")
                        for f in (1, 2, 3)]),
             dict(name="RISER-2", rating="800", fault="50", source="MDB-01",
                  taps=[dict(board="SMDB-T-%d" % f, typical="" if f == 4 else "SMDB-T-4")
                        for f in range(4, 9)])]
    assert rs.apply_risers(s, specs) == []
    lay = layout_schematic(s)
    b1, b2 = sorted(lay.geoms["mdb"].riser_blocks, key=lambda b: b.x)
    assert b2.x > b1.right()             # right of the boards on the first riser
    assert b2.bottom < b1.bottom         # the right riser turns off lowest
    assert not overlaps(lay.drawing)


def test_suggest_typicals():
    s = build_schematic(*sample_tower.build(tower_floors=4))
    boards = list(s.boards())
    assert rs.suggest_typicals([b for b in boards if b.name.startswith("SMDB-T")]) == {
        "SMDB-T-2": "SMDB-T-1", "SMDB-T-3": "SMDB-T-1", "SMDB-T-4": "SMDB-T-1"}


def test_board_ticks_make_the_specs():
    specs = rs.set_mark([], "SMDB-T-1", True)
    specs = rs.set_mark(specs, "SMDB-T-2", True, "riser-1", "SMDB-T-1")
    specs = rs.set_mark(specs, "SMDB-T-3", True, "RISER-2")
    assert [s["name"] for s in specs] == ["RISER-1", "RISER-2"]
    assert rs.board_mark(specs, "smdb-t-2") == (True, "RISER-1", "SMDB-T-1")
    assert rs.board_mark(specs, "SMDB-G") == (False, "", "")
    assert rs.riser_names(specs) == ["RISER-1", "RISER-2", "RISER-3"]
    specs = rs.set_mark(specs, "SMDB-T-3", False)
    assert [s["name"] for s in specs] == ["RISER-1"]       # empty riser dropped
    specs = rs.set_mark(specs, "SMDB-T-2", True, "RISER-1", "")
    assert rs.board_mark(specs, "SMDB-T-2") == (True, "RISER-1", "")


def test_ticked_boards_get_source_rating_and_fault_by_themselves():
    for connected in (False, True):
        specs = []
        for f in range(1, 7):
            specs = rs.set_mark(specs, "SMDB-T-%d" % f, True, "", "" if f == 1 else "SMDB-T-1")
        s, warnings = tower(connected=connected, specs=specs)
        assert warnings == []
        r = s.risers[0]
        assert r.source.name == "MDB-01"           # fed it, else the main board
        assert r.rating == 1000.0                    # 6 x 160A -> 1000A
        assert r.label() == "1000A TPN+E COPPER BUS BAR RISER-1   432.00KW   50KA"
    assert rs.auto_rating([160] * 5) == 800.0 and rs.auto_rating([None]) is None
