# -*- coding: utf-8 -*-
import sample_al_yasat
from sld.editor import CHOICES, FIELDS, Editor
from sld.model import CircuitInfo, EquipmentInfo, build_schematic
from vdrop import calc
from vdrop.parse import Cable


def sample_editor():
    return Editor(build_schematic(*sample_al_yasat.build()))


def ways_by_feeds(editor, board_name):
    b = next(b for b in editor.boards if b.name == board_name)
    return b, dict((w.feeds, w) for w in editor.ways(b.id))


def small(cable=u"(4X120)mm² CU/XLPE/SWA/PVC +(1X70)mm² CU/PVC(E)", vd=True):
    """MDB-1 -> SMDB-1 -> LIGHTS, with the VD feeders the Voltage Drop tool builds."""
    equipment = [EquipmentInfo("MDB-1", "MDB-1"),
                 EquipmentInfo("SMDB-1", "SMDB-1", upstream_protection="250AT/250AF MCCB")]
    circuits = [CircuitInfo("c1", "MDB-1", "1", rating="20 A", poles="3", start_slot=1,
                            fed_equipment_ids=["SMDB-1"], cable=cable, length_m=50.0),
                CircuitInfo("c2", "SMDB-1", "1", "LIGHTS", rating="32 A", poles="3",
                            start_slot=1, branch_load_count=1, connected_kw=10.0,
                            cable=u"(4X6)mm² CU/XLPE/PVC +(1X6)mm² CU/PVC(E)", length_m=30.0),
                CircuitInfo("c3", "SMDB-1", "4", "PUMP", rating="16 A", poles="3",
                            start_slot=4, branch_load_count=1, connected_kw=5.0,
                            cable=u"(4X4)mm² CU/XLPE/PVC")]
    live = None
    if vd:
        live = {"feeders": [
            calc.Feeder("SMDB-1", "MDB-1", "MDB-1", "SMDB-1", target_id="SMDB-1", length=50.0,
                        tcl_kw=150.0, breaker=250.0, cable=Cable(1, 4, 120, "XLPE/SWA/PVC")),
            calc.Feeder("c2", "SMDB-1", "SMDB-1", "LIGHTS", length=30.0, tcl_kw=10.0,
                        breaker=32.0, cable=Cable(1, 4, 6, "XLPE/PVC"))],
            "settings": calc.Settings(), "kinds": {}}
    return Editor(build_schematic(equipment, circuits), live)


def test_boards_in_tree_order_with_their_ways():
    ed = sample_editor()
    assert [b.name for b in ed.roots] == ["MDB-1", "MDB-2"]
    smdb = next(b for b in ed.boards if b.name == "SMDB-GF-M1")
    assert smdb.depth == 1 and smdb.parent_id == ed.roots[0].id
    assert "SMDB-1ST-01" in [c.name for c in smdb.children]
    b, ways = ways_by_feeds(ed, "SMDB-BB-01")
    assert ways["DB-BB-01"].values["at"] == "63" and ways["DB-BB-01"].values["af"] == "100"
    assert ways["DB-BB-01"].values["cores"] == "4" and ways["DB-BB-01"].values["size"] == "16"
    assert set(FIELDS) <= set(ways["DB-BB-01"].values)
    assert all(k in CHOICES for k in ("at", "size", "material", "armour", "spares"))


def test_what_can_be_edited():
    ed = sample_editor()
    _, ways = ways_by_feeds(ed, "SMDB-BB-01")
    added = [w for b in ed.boards for w in ed.ways(b.id) if w.added]
    assert added and all(w.spare for w in added)
    assert not any(added[0].editable(f) for f in FIELDS)             # board spare fields
    revit_spare = next(w for w in ed.ways(ed.roots[0].id) if w.spare)
    assert revit_spare.editable("at") and not revit_spare.editable("size")
    pfc = next(w for w in ed.ways(ed.roots[0].id) if w.kind == "pfc")
    assert pfc.editable("at") and not pfc.editable("length")
    assert ways["ERV-01"].editable("size")


def test_breaker_change_goes_to_the_fed_panel():
    ed = small(vd=False)
    smdb_way = ed.ways("MDB-1")[1]
    assert smdb_way.values["at"] == "250"
    assert ed.set_way(smdb_way.key, "at", "200") == [smdb_way.key]
    (change,) = ed.changes()
    assert change.kind == "breaker" and change.element_id == "SMDB-1"
    assert change.circuit_id == "c1" and change.values["trip"] == 200.0
    lights = ed.ways("SMDB-1")[0]
    ed.set_way(lights.key, "device", "mcb")
    assert lights.values["device"] == "MCB"
    final = [c for c in ed.changes() if c.circuit_id == "c2"][0]
    assert final.element_id is None and final.values["device"] == "MCB"
    assert ed.preview(lights.key)[1] == "32AT / 100AF / MCB"
    ed.mark_saved()
    assert not ed.dirty()


def test_cable_change_and_preview():
    ed = small(vd=False)
    w = ed.ways("MDB-1")[1]
    assert ed.preview(w.key)[0] == u"(4X120)mm² CU/XLPE/SWA/PVC +(1X70)mm² CU/PVC(E)"
    ed.set_way(w.key, "size", "150")
    ed.set_way(w.key, "runs", "2")
    ed.set_way(w.key, "armour", "none")
    text = u"2X(4X150)mm² CU/XLPE/PVC +(1X70)mm² CU/PVC(E)"
    assert ed.preview(w.key)[0] == text
    assert [(c.kind, c.values) for c in ed.changes()] == [("cable", {"text": text})]


def test_bad_values_are_reported():
    ed = small(vd=False)
    w = ed.ways("SMDB-1")[0]
    ed.set_way(w.key, "length", "abc")
    assert "length" in w.errors
    assert any("LIGHTS" not in m and "abc" in m for m in ed.warnings())
    assert not [c for c in ed.changes() if c.kind == "length"]
    ed.set_way(w.key, "length", "42,5")
    assert w.values["length"] == "42.5" and not w.errors
    assert [c.values for c in ed.changes() if c.kind == "length"] == [{"length": 42.5}]


def test_voltage_drop_recalculates_downstream():
    ed = small()
    feeder, lights = ed.ways("MDB-1")[1], ed.ways("SMDB-1")[0]
    before = float(lights.vd)
    assert feeder.vd and before > float(feeder.vd)
    changed = ed.set_way(feeder.key, "size", "50")
    assert feeder.key in changed and lights.key in changed
    assert float(lights.vd) > before
    ed.set_way(feeder.key, "length", "400")
    assert feeder.vd_over and any("over the limit" in m for m in ed.warnings())


def test_length_typed_on_a_final_circuit_gets_a_voltage_drop():
    ed = small()
    pump = ed.ways("SMDB-1")[1]
    assert pump.vd == ""
    ed.set_way(pump.key, "length", "25")
    assert pump.vd not in ("", "n/a")


def test_spares_set_on_the_board():
    ed = small(vd=False)
    b = ed.board("SMDB-1")
    assert b.values["spares"] == "3"
    assert ed.set_board("SMDB-1", "spares", "4") is True
    assert ed.set_board("SMDB-1", "spare_at", "40") is True
    spares = [w for w in ed.ways("SMDB-1") if w.spare]
    assert len(spares) == 4 and spares[0].values["at"] == "40"
    (change,) = [c for c in ed.changes() if c.kind == "spares"]
    assert change.values == {"count": "4", "rating": "40AT/100AF MCCB"}
    assert ed.set_board("SMDB-1", "fault_level", "35kA") is False
    assert [c.values for c in ed.changes() if c.kind == "fault_level"] == [{"text": "35kA"}]


def test_incomer_is_the_breaker_feeding_the_board():
    ed = small(vd=False)
    smdb = ed.board("SMDB-1")
    assert (smdb.values["incomer_at"], smdb.values["incomer_device"]) == ("250", "MCCB")
    ed.set_board("SMDB-1", "incomer_at", "200")
    assert ed.ways("MDB-1")[1].values["at"] == "200"
    ed.set_way(ed.ways("MDB-1")[1].key, "af", "400")
    assert smdb.values["incomer_af"] == "400"
    (change,) = ed.changes()
    assert change.kind == "breaker" and change.element_id == "SMDB-1"
    assert change.values == {"trip": 200.0, "frame": 400.0, "device": "MCCB"}


def test_main_board_incomer_change():
    ed = small(vd=False)
    ed.set_board("MDB-1", "incomer_at", "1600")
    ed.set_board("MDB-1", "incomer_device", "acb")
    (change,) = ed.changes()
    assert change.kind == "incomer" and change.element_id == "MDB-1"
    assert change.values == {"trip": 1600.0, "frame": None, "device": "ACB"}


def test_main_board_has_a_row_for_its_transformer_cable():
    ed = small()
    tx = ed.ways("MDB-1")[0]
    assert tx.incoming and tx.label == "TX" and tx.feeds == "FROM TRANSFORMER"
    assert tx.values["length"] == "" and tx.vd == ""
    assert all(tx.editable(f) for f in FIELDS)
    assert not any(w.incoming for w in ed.ways("SMDB-1"))
    lights = ed.ways("SMDB-1")[0]
    # no transformer row yet: the totals start at the main board
    before = float(lights.vd)
    changed = ed.set_way(tx.key, "length", "20")
    ed.set_way(tx.key, "size", "300")
    assert tx.vd not in ("", "n/a") and lights.key in changed
    assert float(lights.vd) > before
    kinds = dict((c.kind, c) for c in ed.changes())
    assert kinds["length"].element_id == "MDB-1" and kinds["length"].circuit_id is None
    assert kinds["cable"].element_id == "MDB-1" and "300" in kinds["cable"].values["text"]
    # its breaker is the main board's incomer
    ed.set_way(tx.key, "at", "1600")
    assert ed.board("MDB-1").values["incomer_at"] == "1600"
    assert "breaker" not in [c.kind for c in ed.changes()]
    assert [c.values["trip"] for c in ed.changes() if c.kind == "incomer"] == [1600.0]
    ed.set_board("MDB-1", "incomer_at", "2000")
    assert tx.values["at"] == "2000"


def test_transformer_cable_row_reads_what_is_on_the_board():
    ed = small()
    ed.vd["feeders"].append(calc.Feeder("MDB-1", "TR:MDB-1", "TR", "MDB-1", target_id="MDB-1",
                                        length=15.0, tcl_kw=150.0, source_kind=calc.TRANSFORMER,
                                        cable=Cable(2, 4, 240, "XLPE/SWA/PVC")))
    ed2 = Editor(ed.schematic, ed.vd)
    tx = ed2.ways("MDB-1")[0]
    assert (tx.values["length"], tx.values["runs"], tx.values["size"]) == ("15", "2", "240")
    assert tx.vd and not ed2.dirty()


def test_transformer_vd_typed_by_hand():
    ed = small()
    tx, lights = ed.ways("MDB-1")[0], ed.ways("SMDB-1")[0]
    before = float(lights.vd)
    ed.set_board("MDB-1", "tx_vd", "0.8 %")
    assert ed.board("MDB-1").values["tx_vd"] == "0.8"
    assert tx.vd == "0.80" and abs(float(lights.vd) - before - 0.8) < 0.01
    assert [c.values for c in ed.changes() if c.kind == "tx_vd"] == [{"value": 0.8}]
    ed.set_board("MDB-1", "tx_vd", "abc")
    assert ed.board("MDB-1").errors and any("transformer V.D" in m for m in ed.warnings())
    assert not [c for c in ed.changes() if c.kind == "tx_vd"]
    ed.set_board("MDB-1", "tx_vd", "")
    assert tx.vd == "" and abs(float(lights.vd) - before) < 0.01
    assert not ed.has_incoming("SMDB-1") and ed.has_incoming("MDB-1")


def test_typed_vd_row_in_the_calculation():
    rows = calc.calculate([
        calc.Feeder("MDB", "TR:MDB", "TR", "MDB", target_id="MDB", tcl_kw=100.0,
                    source_kind=calc.TRANSFORMER, typed_vd=1.2),
        calc.Feeder("SMDB", "MDB", "MDB", "SMDB", target_id="SMDB", length=20.0, tcl_kw=50.0,
                    breaker=125.0, cable=Cable(1, 4, 50, "XLPE/SWA/PVC"))]).rows()
    mdb, smdb = list(rows)
    assert mdb.vd_percent == 1.2 and mdb.total_percent == 1.2
    assert not [p for p in mdb.problems if "Length" in p or "size" in p]
    assert "V.D 1.2% typed" in mdb.remarks()
    assert abs(smdb.total_percent - (1.2 + smdb.vd_percent)) < 1e-9


def test_own_vd_when_the_total_is_not_known():
    from sld import studio
    ed = small()
    ed.set_board("MDB-1", "tx_vd", "")
    tx = ed.ways("MDB-1")[0]
    ed.set_way(tx.key, "length", "20")       # no cable size: the row is incomplete
    lights = ed.ways("SMDB-1")[0]
    assert lights.vd_partial and lights.vd.endswith(" own")
    assert studio.way_state(lights) == "warn" and "No total yet" in lights.vd_tip
