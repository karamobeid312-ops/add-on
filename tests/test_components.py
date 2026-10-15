# -*- coding: utf-8 -*-
"""PFC banks and transfer switches are components, never drawn as boards."""
import sample_tower
from sld.layout import layout_schematic
from sld.model import ATS, PFC, TO_UPS, CircuitInfo, EquipmentInfo, build_schematic
from test_layout import overlaps


def model():
    eq, c = sample_tower.build(tower_floors=0)
    eq += [EquipmentInfo("pfc", "PFC-01", "Ground Floor", 0.0, family_name="Capacitor Bank"),
           EquipmentInfo("ats", "ATS-01", "Ground Floor", 0.0, location="LV RM", mains_rating="630"),
           EquipmentInfo("emdb", "EMDB-G", "Ground Floor", 0.0),
           EquipmentInfo("ats2", "ATS-02", "Ground Floor", 0.0, mains_rating="400"),
           EquipmentInfo("emdb2", "EMDB-2", "Ground Floor", 0.0)]
    c += [CircuitInfo("c-pfc", "mdb", "3", rating="800", poles="3", fed_equipment_ids=["pfc"]),
          CircuitInfo("c-ats", "mdb", "4", rating="630", poles="3", fed_equipment_ids=["ats"]),
          # the generator side of ATS-01: a second supply is no warning
          CircuitInfo("c-gen", "smdb-g", "9", rating="630", poles="3", fed_equipment_ids=["ats"]),
          CircuitInfo("c-e", "ats", "1", poles="3", fed_equipment_ids=["emdb"]),
          CircuitInfo("c-e2", "ats2", "1", poles="3", fed_equipment_ids=["emdb2"],
                      cable="(4X150)mm2 FR6")]
    for i in range(3):
        c.append(CircuitInfo("c-e%d" % i, "emdb", str(i + 1), "LOAD %d" % i, rating="63", poles="3"))
        c.append(CircuitInfo("c-f%d" % i, "emdb2", str(i + 1), "FAN %d" % i, rating="32", poles="3"))
    return build_schematic(eq, c)


def test_pfc_and_ats_are_not_boards():
    s = model()
    names = sorted(b.name for b in s.boards())
    assert names == ["EMDB-2", "EMDB-G", "MDB-01", "SMDB-G"]
    assert not s.warnings
    mdb = next(b for b in s.boards() if b.name == "MDB-01")
    kinds = dict((w.name, w.kind) for w in mdb.ways)
    assert kinds["PFC-01"] == PFC and kinds["ATS-01"] == TO_UPS
    assert mdb.pass_throughs[0].kind == ATS
    emdb = next(b for b in s.boards() if b.name == "EMDB-G")
    assert emdb.parent is mdb and emdb.feed_pass_through is mdb.pass_throughs[0]
    # an ATS with no supply in the model: the board it feeds is drawn with it below
    emdb2 = next(b for b in s.boards() if b.name == "EMDB-2")
    assert emdb2.is_main and emdb2.ats.name == "ATS-02"


def test_components_drawn_clear():
    lay = layout_schematic(model())
    texts = [t.text for t in lay.drawing.texts]
    assert "ATS-01" in texts and "ATS-02" in texts and "630A,4P" in "\n".join(texts)
    assert "FROM TAQA" in texts and texts.count("FROM TAQA") == 1     # not under EMDB-2
    assert not overlaps(lay.drawing)


def test_isolator_cable_split_like_a_db_way():
    s = build_schematic(*sample_tower.build(tower_floors=0))
    smdb = next(b for b in s.boards() if b.name == "SMDB-G")
    lift = next(w for w in smdb.ways if w.name == "LIFT 1")
    # no earth part in the model: the office earth is added, printed right of the line
    assert lift.rating_lines() == [u"(4X10)mm² CU/XLPE/SWA/PVC", u"+(1X10)mm² CU/PVC(E)"]


def test_earth_pits_are_not_drawn_as_db_boxes():
    eq, c = sample_tower.build(tower_floors=0)
    eq += [EquipmentInfo("pit%d" % i, "Earth Pit With Test Link", "Ground Floor", 0.0)
           for i in range(3)]
    eq += [EquipmentInfo("db-x", "DB-AILAB", "Ground Floor", 0.0)]
    s = build_schematic(eq, c)
    assert [e.name for e in s.loose_dbs] == ["DB-AILAB"]


def test_jogs_ordered_so_risers_do_not_cross():
    from sld.layout import _order_jogs
    # A comes up at 100 and jogs left to 0; B comes up at 150 and jogs left to 50.
    # With A on top, B's riser up at 50 would cross A's line: B goes on top.
    a, b = [0, 100.0, 0.0, 0], [0, 150.0, 50.0, 0]
    assert _order_jogs([a, b]) == [b, a]


def test_way_numbers_under_the_busbar_on_sub_boards():
    s = build_schematic(*sample_tower.build(tower_floors=0))
    lay = layout_schematic(s)
    g = lay.geoms["smdb-g"]
    labels = [t for t in lay.drawing.texts if t.text == "1" and g.left < t.x < g.right]
    assert labels and all(t.y < g.bus_y for t in labels)


def _coincident_risers(lay):
    segs = []
    for i, f in enumerate(lay.feeds):
        for a, b in zip(f.points, f.points[1:]):
            if abs(a[0] - b[0]) < 1e-6:
                segs.append((i, a[0], min(a[1], b[1]), max(a[1], b[1])))
    return [(p, q) for n, p in enumerate(segs) for q in segs[n + 1:]
            if p[0] != q[0] and abs(p[1] - q[1]) < 0.5 and min(p[3], q[3]) - max(p[2], q[2]) > 0.5]


def test_risers_round_the_same_board_get_their_own_lane():
    eq, c = sample_tower.build(connected=True, tower_floors=6)
    lay = layout_schematic(build_schematic(eq, c))
    assert len(lay.feeds) > 3
    assert not _coincident_risers(lay)


def test_incomer_never_sits_on_a_way_line():
    s = build_schematic(*sample_tower.build(connected=True, tower_floors=6))
    lay = layout_schematic(s)
    for g in lay.geoms.values():
        if hasattr(g, "way_offsets"):
            assert all(abs(o - g.incomer_offset) > 1.0 for o in g.way_offsets), g.name
