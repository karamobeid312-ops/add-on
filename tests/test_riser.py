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


def test_riser_layout_compact_and_clear():
    for connected in (False, True):
        s, _ = tower(connected=connected)
        lay = layout_schematic(s)
        problems = overlaps(lay.drawing)
        assert not problems, problems[:10]
        mdb = lay.geoms["mdb"]
        block = mdb.riser_blocks[0]
        assert block.bottom > mdb.top
        master = lay.geoms["t1"]
        assert master.left > block.box_left() + block.box_width     # beside the typicals
        assert block.bottom < master.bottom < block.top
        # the tower floors make no floor bands: only SUBSTATION and the podium floor
        assert [label for label, _ in lay.bands] == ["SUBSTATION", "GROUND FLOOR"]
        assert lay.bands[1][1] > block.top


def test_two_risers_stack_without_crossing():
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
    assert b2.top < b1.bottom            # the right riser sits lower
    assert b1.x < b2.x
    assert not overlaps(lay.drawing)


def test_suggest_typicals_and_grid_helpers():
    s = build_schematic(*sample_tower.build(tower_floors=4))
    boards = list(s.boards())
    assert rs.suggest_typicals([b for b in boards if b.name.startswith("SMDB-T")]) == {
        "SMDB-T-2": "SMDB-T-1", "SMDB-T-3": "SMDB-T-1", "SMDB-T-4": "SMDB-T-1"}
    spec = rs.new_spec([], boards)
    assert spec["name"] == "RISER-1" and spec["source"] == "MDB-01" and spec["fault"] == "50"
    assert rs.new_spec([spec], boards)["name"] == "RISER-2"
    rows = rs.riser_rows(spec, boards)
    assert [r["board"] for r in rows] == ["SMDB-G"] + ["SMDB-T-%d" % f for f in range(1, 5)]
    assert rows[1]["rating"] == "160" and not rows[1]["on"]
    for r in rows[1:]:
        r["on"] = True
    assert rs.suggest_rows(rows, boards) == 3
    spec["taps"] = rs.taps_from_rows(rows)
    assert [t["typical"] for t in spec["taps"]] == ["", "SMDB-T-1", "SMDB-T-1", "SMDB-T-1"]
    assert rs.riser_rows(spec, boards, taken=["SMDB-G"])[0]["board"] == "SMDB-T-1"
    assert rs.way_choices(boards, "MDB-01") == [rs.NEW_WAY, "1"]
    assert rs.clean_specs([spec])[0]["taps"][1] == {"board": "SMDB-T-2", "rating": "160",
                                                    "typical": "SMDB-T-1"}
