# -*- coding: utf-8 -*-
"""Transformer and PFC typed in Power Studio for an MDB / EMDB."""
import sample_tower
from sld import supply as sp
from sld.layout import layout_schematic
from sld.model import PFC, CircuitInfo, EquipmentInfo, build_schematic
from test_layout import overlaps

TX = {"name": "TR-01", "kva": "1000", "voltage": "11/0.4kV", "type": "OIL TYPE TRANSFORMER",
      "cable": u"7 SC 630mm² Cu/XLPE/AWA/PVC", "mv": "MV CABLE FROM TAQA"}


def model():
    eq, c = sample_tower.build(tower_floors=0)
    eq = [e for e in eq if e.id != "tr"]
    c = [x for x in c if x.source_id != "tr"]
    eq.append(EquipmentInfo("emdb", "EMDB-01", "Ground Floor", 0.0,
                            upstream_protection="630AT/630AF MCCB"))
    for i in range(3):
        c.append(CircuitInfo("ce%d" % i, "emdb", str(i + 1), "PUMP %d" % i, rating="63",
                             poles="3", connected_kw=30))
    return build_schematic(eq, c)


def test_transformer_and_pfc_drawn_as_typed():
    s = model()
    specs = [{"board": "MDB-01", "tx": TX,
              "pfc": {"kvar": "300", "rating": "600", "cable": "2X(4X150)mm2 CU"}},
             {"board": "EMDB-01", "tx": dict(TX, name="TR-02", kva="500"), "pfc": {"kvar": "150"}}]
    assert sp.apply_supply(s, specs) == []
    mdb, emdb = s.roots[0], s.roots[1]
    assert (mdb.name, emdb.name) == ("MDB-01", "EMDB-01")
    assert mdb.transformer.name == "TR-01"
    assert mdb.transformer.description == ["11/0.4kV", "1000KVA", "OIL TYPE TRANSFORMER"]
    assert emdb.is_main and emdb.transformer.name == "TR-02"
    pfc = [w for w in mdb.ways if w.kind == PFC]
    assert len(pfc) == 1 and pfc[0].pfc_text == "(300 KVAR)" and pfc[0].trip() == 600
    lay = layout_schematic(s)
    texts = [t.text for t in lay.drawing.texts]
    assert texts.count("MV CABLE FROM TAQA") == 2 and "TR-02" in texts
    assert "POWER FACTOR CORRECTION (300 KVAR)" in texts
    assert not overlaps(lay.drawing)


def test_pfc_goes_before_the_spares():
    s = model()
    smdb = next(b for b in s.boards() if b.name == "SMDB-G")
    labels = [w.label for w in smdb.ways]
    sp.apply_supply(s, [{"board": "SMDB-G", "pfc": {"kvar": "50"}}])
    kinds = [w.kind for w in smdb.ways]
    first_spare = kinds.index("spare")
    assert kinds[first_spare - 1] == PFC
    assert [w.label for w in smdb.ways] == labels + [str(int(labels[-1]) + 1)]


def test_specs_set_and_clean():
    specs = sp.set_supply([], "MDB-01", "tx", TX)
    specs = sp.set_supply(specs, "MDB-01", "pfc", {"kvar": " 300 "})
    tx, pfc = sp.board_supply(specs, "mdb-01")
    assert tx["name"] == "TR-01" and pfc == {"kvar": "300", "rating": "", "cable": ""}
    specs = sp.set_supply(specs, "MDB-01", "tx", None)
    specs = sp.set_supply(specs, "MDB-01", "pfc", None)
    assert specs == []
