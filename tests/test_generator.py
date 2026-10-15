# -*- coding: utf-8 -*-
"""Standby generator on a life safety board, through an ATS (office SLD)."""
import sample_tower
from sld import generator as gn
from sld.layout import SUBSTATION_BAND, layout_schematic
from sld.model import GENERATOR, CircuitInfo, EquipmentInfo, build_schematic
from test_layout import overlaps


def model(extra_eq=(), extra_c=()):
    eq, c = sample_tower.build(tower_floors=0)
    eq += [EquipmentInfo("emdb", "EMDB-G", "Ground Floor", 0.0, location="ELEC",
                         upstream_protection="630AT/630AF MCCB")] + list(extra_eq)
    c += [CircuitInfo("c-e", "mdb", "4", rating="630", poles="3", fed_equipment_ids=["emdb"],
                      cable="2x(4X185)mm2 FR6 +2x(1x95)mm2 FR (E)")] + list(extra_c)
    for i in range(3):
        c.append(CircuitInfo("c-e%d" % i, "emdb", str(i + 1), "LIFT %d" % i, rating="63",
                             poles="3", connected_kw=40.0 + i))
    return build_schematic(eq, c)


def test_auto_kva_is_cl_times_1_2_times_1_2_next_rating():
    assert gn.auto_kva(123.0) == 200          # 177 kVA
    assert gn.auto_kva(208.0) == 300          # 299.5 kVA
    assert gn.auto_kva(208.4) == 350          # 300.1 kVA
    assert gn.auto_kva(100.0) == 150
    assert gn.auto_kva(None) is None


def test_generator_board_drawn_beside_its_mdb_with_ats():
    s = model()
    warnings = gn.apply_generators(s, [{"board": "EMDB-G"}])
    assert not warnings
    emdb = next(b for b in s.boards() if b.name == "EMDB-G")
    gen = emdb.generator
    assert gen.name == "G-01" and gen.kva == 200
    assert gen.normal_board.name == "MDB-01" and gen.normal_way.name == "EMDB-G"
    assert gen.ats.info() == ["630A,4P", "LOCATION: ELEC"]
    assert gen.gen_cable == "2x(4X185)mm2 FR6"
    assert gen.lines() == ["G-01 PRIME GENERATOR", "0.4kV, 50Hz, 1500 RPM", "200 kVA"]
    assert emdb.parent is None and [r.name for r in s.roots][:2] == ["MDB-01", "EMDB-G"]
    lay = layout_schematic(s)
    g, mdb = lay.geoms["emdb"], lay.geoms["mdb"]
    assert g.band == SUBSTATION_BAND and g.left > mdb.extent_right()
    assert not overlaps(lay.drawing)
    texts = [t.text for t in lay.drawing.texts]
    assert "G" in texts and "ATS" in texts and gn.EARTH_TEXT in texts


def test_spec_board_missing_is_a_warning():
    s = model()
    assert gn.apply_generators(s, [{"board": "NOPE"}]) == ["Generator: NOPE is not in the model."]


def test_generator_equipment_is_never_a_board():
    s = model([EquipmentInfo("gen", "G-01", "Ground Floor", 0.0, family_name="Diesel Generator"),
               EquipmentInfo("ats", "ATS-01", "Ground Floor", 0.0, mains_rating="400"),
               EquipmentInfo("emdb2", "EMDB-2", "Ground Floor", 0.0)],
              [CircuitInfo("c-g", "gen", "1", poles="3", fed_equipment_ids=["ats"]),
               CircuitInfo("c-a", "ats", "1", poles="3", fed_equipment_ids=["emdb2"]),
               CircuitInfo("c-f", "emdb2", "1", "FAN", rating="32", poles="3")])
    assert "G-01" not in [b.name for b in s.boards()]
    emdb2 = next(b for b in s.boards() if b.name == "EMDB-2")
    assert emdb2.model_generator.name == "G-01"
    gn.apply_generators(s, [])
    assert emdb2.generator.name == "G-01" and emdb2.generator.ats.name == "ATS-01"
    assert emdb2.generator.normal_text == "FROM TAQA"
    assert not overlaps(layout_schematic(s).drawing)


def test_set_generator_add_and_remove():
    specs = gn.set_generator([], "EMDB-G", True)
    specs = gn.set_generator(specs, "EMDB-2", True)
    assert [s["name"] for s in specs] == ["G-01", "G-02"]
    assert gn.board_generator(specs, "emdb-g")["name"] == "G-01"
    specs = gn.set_generator(specs, "EMDB-G", False)
    assert gn.board_generator(specs, "EMDB-G") is None
    assert gn.clean_specs(specs + [{"board": ""}]) == [{"board": "EMDB-2", "name": "G-02", "kva": ""}]


def test_generator_role():
    s = model([EquipmentInfo("gen", "GEN-01", "Ground Floor", 0.0)])
    assert "GEN-01" not in [b.name for b in s.boards()]
    assert GENERATOR == "generator"
