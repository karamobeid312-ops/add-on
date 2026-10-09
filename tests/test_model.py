# -*- coding: utf-8 -*-
from sld.model import (BOARD, DB_BOX, FEEDER, ISOLATOR, MAIN_BOARD, PFC,
                       SPARE, TO_UPS, CircuitInfo, EquipmentInfo, build_schematic,
                       natural_key, way_labels)


def eq(name, **kw):
    return EquipmentInfo(name, name, **kw)


def ckt(src, slot, fed=(), poles="3", **kw):
    return CircuitInfo("%s/%s" % (src, slot), src, str(slot), poles=poles,
                       start_slot=slot, fed_equipment_ids=list(fed), **kw)


def boards(s):
    return dict((b.name, b) for b in s.boards())


def test_roles_main_board_db():
    equipment = [eq("MDB-1"), eq("SMDB-1"), eq("LDB-1"), eq("PANEL-X")]
    circuits = [ckt("MDB-1", 1, ["SMDB-1"]), ckt("SMDB-1", 1, ["LDB-1"]),
                ckt("SMDB-1", 4, ["PANEL-X"])]
    s = build_schematic(equipment, circuits)
    b = boards(s)
    assert [r.name for r in s.roots] == ["MDB-1"]
    assert b["MDB-1"].role == MAIN_BOARD
    assert b["SMDB-1"].role == BOARD
    assert "LDB-1" not in b and "PANEL-X" not in b       # drawn as DB boxes
    assert [w.kind for w in b["SMDB-1"].ways] == [DB_BOX, DB_BOX]
    assert b["MDB-1"].ways[0].kind == FEEDER
    assert b["SMDB-1"].parent is b["MDB-1"]


def test_board_name_pattern_makes_board_even_without_sub_panels():
    equipment = [eq("MDB-1"), eq("SMDB-RF-02"), eq("USMDB-GF")]
    circuits = [ckt("MDB-1", 1, ["SMDB-RF-02"]), ckt("MDB-1", 4, ["USMDB-GF"]),
                ckt("SMDB-RF-02", 1, load_name="VRF-07", branch_load_count=1)]
    b = boards(build_schematic(equipment, circuits))
    assert b["SMDB-RF-02"].role == BOARD and b["USMDB-GF"].role == BOARD
    assert b["SMDB-RF-02"].ways[0].kind == ISOLATOR
    assert b["SMDB-RF-02"].ways[0].name == "VRF-07"


def test_symbol_override():
    equipment = [eq("MDB-1"), eq("DB-X", symbol="board")]
    b = boards(build_schematic(equipment, [ckt("MDB-1", 1, ["DB-X"])]))
    assert b["DB-X"].role == BOARD


def test_transformer_goes_under_main_board():
    equipment = [eq("TR-01", part_type="transformer", description=["1000KVA"]),
                 eq("MDB-1")]
    circuits = [ckt("TR-01", 1, ["MDB-1"], cable=u"7 SC 630mm² Cu/XLPE/AWA/PVC")]
    s = build_schematic(equipment, circuits)
    assert [r.name for r in s.roots] == ["MDB-1"]
    assert s.roots[0].transformer.name == "TR-01"
    assert s.roots[0].equipment.incoming_cable == u"7 SC 630mm² Cu/XLPE/AWA/PVC"


def test_way_kinds_spare_pfc_isolator():
    circuits = [ckt("MDB-1", 1, load_name="PFC", branch_load_count=1),
                ckt("MDB-1", 4, load_name="EV-01", branch_load_count=1),
                ckt("MDB-1", 7, is_spare=True),
                ckt("MDB-1", 10, load_name="Pump", symbol="spare")]
    ways = build_schematic([eq("MDB-1")], circuits).roots[0].ways
    assert [w.kind for w in ways] == [PFC, ISOLATOR, SPARE, SPARE]
    assert [w.label for w in ways] == ["1", "2", "3", "4"]
    assert ways[2].name == "SPARE"


def test_way_labels_are_sequential_whatever_the_slot_numbering():
    # two-column panel: 3-pole breakers start at slots 1, 2, 7, 8
    circuits = [ckt("B", 1), ckt("B", 2), ckt("B", 7), ckt("B", 8)]
    assert way_labels(circuits) == ["1", "2", "3", "4"]


def test_way_labels_single_phase_share_a_way():
    circuits = [ckt("B", 1), ckt("B", 4, poles="1"), ckt("B", 5, poles="1"),
                ckt("B", 6, poles="1"), ckt("B", 7, poles="1"), ckt("B", 10)]
    assert way_labels(circuits) == ["1", "R2", "Y2", "B2", "R3", "4"]
    assert way_labels(circuits, phases=1) == ["1", "2", "3", "4", "5", "6"]
    assert way_labels(circuits, numbering="revit") == ["1", "4", "5", "6", "7", "10"]


def test_transformer_fed_from_board_sits_between_boards():
    # US style: SWB (fed by utility transformer) -> T-2A -> panel PP-2A
    equipment = [eq("T-SVC", part_type="transformer"), eq("SWB"),
                 eq("T-2A", part_type="transformer"), eq("PP-2A"), eq("LP-1")]
    circuits = [ckt("T-SVC", 1, ["SWB"]), ckt("SWB", 1, ["T-2A"]),
                ckt("T-2A", 1, ["PP-2A"]), ckt("PP-2A", 1, ["LP-1"])]
    s = build_schematic(equipment, circuits)
    b = boards(s)
    assert [r.name for r in s.roots] == ["SWB"]
    assert s.roots[0].transformer.name == "T-SVC"
    assert b["PP-2A"].role == BOARD
    assert b["PP-2A"].parent is b["SWB"]
    pt = b["SWB"].pass_throughs[0]
    assert pt.kind == "transformer" and pt.outputs == [b["PP-2A"]]
    assert b["SWB"].ways[0].kind == TO_UPS


def test_ups_between_boards_with_two_inputs():
    equipment = [eq("MDB-1"), eq("SMDB-GF"), eq("UPS", family_name="UPS 60kVA"),
                 eq("USMDB-GF"), eq("UDB-01")]
    circuits = [ckt("MDB-1", 1, ["SMDB-GF"]),
                ckt("SMDB-GF", 1, ["UPS"]), ckt("SMDB-GF", 4, ["UPS"]),
                ckt("UPS", 1, ["USMDB-GF"]), ckt("USMDB-GF", 1, ["UDB-01"])]
    s = build_schematic(equipment, circuits)
    b = boards(s)
    assert s.warnings == []
    gf = b["SMDB-GF"]
    assert [w.kind for w in gf.ways] == [TO_UPS, TO_UPS]
    assert len(gf.pass_throughs) == 1 and len(gf.pass_throughs[0].input_ways) == 2
    assert b["USMDB-GF"].feed_pass_through is gf.pass_throughs[0]
    assert b["USMDB-GF"].parent is gf and b["USMDB-GF"] in gf.children


def test_double_feed_warns():
    equipment = [eq("MDB-1"), eq("MDB-2"), eq("SMDB-1")]
    circuits = [ckt("MDB-1", 1, ["SMDB-1"]), ckt("MDB-2", 1, ["SMDB-1"])]
    s = build_schematic(equipment, circuits)
    assert any("more than one circuit" in w for w in s.warnings)
    assert [b.name for b in s.boards()].count("SMDB-1") == 1


def test_feed_loop_is_broken_with_warning():
    equipment = [eq("SMDB-A"), eq("SMDB-B")]
    circuits = [ckt("SMDB-A", 1, ["SMDB-B"]), ckt("SMDB-B", 1, ["SMDB-A"])]
    s = build_schematic(equipment, circuits)
    assert sorted(b.name for b in s.boards()) == ["SMDB-A", "SMDB-B"]
    assert any("loop" in w for w in s.warnings)


def test_rating_lines():
    c = CircuitInfo("c", "s", "1", rating="63 A", poles="3",
                    cable=u"4Cx16mm² Cu/XLPE/PVC + 1Cx16mm² Cu/XLPE/PVC")
    from sld.model import Way
    assert Way(c, FEEDER, "1", "X").rating_lines() == [
        u"4Cx16mm² Cu/XLPE/PVC", u"+ 1Cx16mm² Cu/XLPE/PVC"]
    assert Way(c, SPARE, "1", "SPARE").rating_lines() == []
    assert Way(c, PFC, "1", "PFC").rating_lines() == []


def test_breaker_lines_trip_and_frame():
    from sld.model import breaker_lines, frame_rating
    assert breaker_lines("40 A") == ["40AT", "100AF", "MCCB"]
    assert breaker_lines("125 A") == ["125AT", "160AF", "MCCB"]
    assert breaker_lines("125 A", frame="250") == ["125AT", "250AF", "MCCB"]
    assert breaker_lines(20.0) == ["20AT", "100AF", "MCCB"]
    assert breaker_lines("") == ["MCCB"]
    assert frame_rating(5000, (100, 160)) == 5000      # beyond the largest frame
    spare = CircuitInfo("s", "x", "9", rating="40 A", is_spare=True)
    assert spare.breaker_lines() == ["40AT", "100AF", "MCCB"]


def test_supply_text():
    e = EquipmentInfo("x", "SMDB-2F", mains_rating=160.0, fault_level="35 kA")
    assert e.supply_text() == "160A,3PH+N+E,35kA FOR 1 SEC"
    assert EquipmentInfo("y", "DB", phases=1).supply_text() == "1PH+N+E"
    assert EquipmentInfo("z", "DB", neutral=False, fault_level="50000").supply_text() == \
        "3PH+E,50kA FOR 1 SEC"
    e.incomer_rating = "125 A"
    assert e.incomer_lines() == ["125AT", "160AF", "MCCB"]


def test_main_incomer_is_mccb_below_800a():
    e = EquipmentInfo("x", "SMDB-01", incomer_rating=160.0)
    assert e.main_incomer_lines() == ["160AT", "160AF", "MCCB"]
    e.incomer_rating = 1600.0
    assert e.main_incomer_lines() == ["1600AT", "1600AF", "ACB"]
    e.incomer_rating = None
    assert e.main_incomer_lines() == ["ACB"]


def test_sample_drawing_structure():
    import sample_al_yasat
    s = build_schematic(*sample_al_yasat.build())
    b = boards(s)
    assert s.warnings == []
    assert [r.name for r in s.roots] == ["MDB-1", "MDB-2"]
    assert sorted(b) == sorted(["MDB-1", "MDB-2", "SMDB-GF-M1", "SMDB-GF-M2", "SMDB-BB-01",
                                "USMDB-GF-M", "SMDB-1ST-01", "SMDB-2ND-01",
                                "SMDB-RF-01", "SMDB-RF-02"])
    rf = b["SMDB-RF-01"]
    assert [w.label for w in rf.ways][7:12] == ["8", "R9", "Y9", "B9", "10"]
    assert [w.label for w in rf.ways][-1] == "18"
    assert b["USMDB-GF-M"].parent.name == "SMDB-GF-M1"
    assert b["MDB-1"].transformer.name == "TR-01"


def test_natural_key():
    assert sorted(["10", "2", "1,3,5", "B", "a"], key=natural_key) == ["1,3,5", "2", "10", "a", "B"]


def _smdb_with_loads():
    equipment = [eq("SMDB-2F"),
                 eq("ACB-Z1-2F", connected_kw=2.5, demand_kw=2.2),
                 eq("LDB-Z1-2F", connected_kw=13.4, demand_kw=12.0),
                 eq("UPS", family_name="UPS"), eq("USMDB")]
    circuits = [ckt("SMDB-2F", 1, ["ACB-Z1-2F"], length_m=100.0, vd_percent=2.971),
                ckt("SMDB-2F", 4, ["LDB-Z1-2F"], length_m=50.0),
                ckt("SMDB-2F", 7, load_name="AHU-1", branch_load_count=1, connected_kw=4.0),
                ckt("SMDB-2F", 10, ["UPS"]), ckt("SMDB-2F", 13, ["UPS"]),
                ckt("SMDB-2F", 16, is_spare=True),
                ckt("UPS", 1, ["USMDB"])]
    return build_schematic(equipment, circuits)


def test_way_loads_from_db_or_final_circuit():
    ways = boards(_smdb_with_loads())["SMDB-2F"].ways
    assert ways[0].loads() == (2.5, 2.2)
    assert ways[2].loads() == (4.0, 4.0)          # final circuit: DL = CL
    assert ways[5].loads() == (None, None)        # spare


def test_length_and_vd_printed_along_the_way():
    ways = boards(_smdb_with_loads())["SMDB-2F"].ways
    assert ways[0].vd_text() == "L:100m  V.D:2.97%"
    assert ways[0].rating_lines()[-1] == "L:100m  V.D:2.97%"
    assert ways[1].vd_text() == "L:50m"           # no V.D worked out
    assert ways[2].vd_text() == ""


def test_load_totals_count_each_equipment_once():
    smdb = boards(_smdb_with_loads())["SMDB-2F"]
    cl, df, dl = smdb.load_totals()
    assert abs(cl - (2.5 + 13.4 + 4.0)) < 1e-9    # UPS has no load: skipped
    assert abs(dl - (2.2 + 12.0 + 4.0)) < 1e-9
    assert abs(df - dl / cl) < 1e-9
    ups = [w for w in smdb.ways if w.kind == TO_UPS]
    ups[0].target.connected_kw = ups[0].target.demand_kw = 10.0
    assert abs(smdb.load_totals()[0] - 29.9) < 1e-9   # two ways, one UPS


def test_no_load_totals_without_loads():
    s = build_schematic([eq("SMDB-1"), eq("LDB-1")], [ckt("SMDB-1", 1, ["LDB-1"])])
    assert boards(s)["SMDB-1"].load_totals() is None
