# -*- coding: utf-8 -*-
from sld import sizing
from sld.editor import Editor
from sld.model import CircuitInfo, EquipmentInfo, build_schematic


def test_table_rows():
    s = sizing.size_for(45)
    assert s.cable.text() == u"(4X25)mm² CU/XLPE/SWA/PVC +(1X16)mm² CU/PVC(E)"
    assert (s.trip, s.frame, s.device) == (100, 100, "MCCB")
    assert sizing.size_for(15).cable.size == 10 and sizing.size_for(15).trip == 40
    assert sizing.size_for(15.5).cable.size == 16
    assert sizing.size_for(130).cable.size == 120 and sizing.size_for(130).trip == 250
    s = sizing.size_for(350)
    assert s.cable.text().startswith(u"2X(4X240)mm²") and s.trip == 800


def test_breaker_ranges_split_by_load():
    assert sizing.size_for(20).trip == 63 and sizing.size_for(30).trip == 80
    assert sizing.size_for(110).trip == 225 and sizing.size_for(120).trip == 250


def test_earth_sizes():
    assert [sizing.earth_size(s) for s in (10, 16, 25, 35, 50, 95, 120, 240, 300)] == \
        [10, 16, 16, 16, 25, 50, 70, 120, 150]


def test_large_breakers_are_acbs_and_limits():
    s = sizing.size_for(900)
    assert s.trip == 2000 and s.device == "ACB" and s.frame == 2000
    assert sizing.size_for(1200) is None and sizing.size_for(0) is None
    assert sizing.size_for(None) is None


def _editor():
    equipment = [EquipmentInfo("MDB-1", "MDB-1"),
                 EquipmentInfo("SMDB-1", "SMDB-1", connected_kw=45.0, demand_kw=30.0),
                 EquipmentInfo("DB-1", "DB-1", connected_kw=12.0, demand_kw=9.0),
                 EquipmentInfo("DB-2", "DB-2")]
    circuits = [CircuitInfo("c1", "MDB-1", "1", poles="3", start_slot=1,
                            fed_equipment_ids=["SMDB-1"]),
                CircuitInfo("c2", "SMDB-1", "1", poles="3", start_slot=1,
                            fed_equipment_ids=["DB-1"]),
                CircuitInfo("c3", "SMDB-1", "4", poles="3", start_slot=4,
                            fed_equipment_ids=["DB-2"]),
                CircuitInfo("c4", "SMDB-1", "7", "PUMP", rating="16 A", poles="3",
                            start_slot=7, branch_load_count=1, connected_kw=50.0)]
    return Editor(build_schematic(equipment, circuits))


def test_auto_size_smdb_and_db_only_by_connected_load():
    ed = _editor()
    changed, messages = ed.auto_size()
    smdb = ed.way("c1")
    assert smdb.values["size"] == "25" and smdb.values["at"] == "100"   # 45 kW CL, not 30 DL
    assert smdb.sized
    db = ed.way("c2")
    assert db.values["size"] == "10" and db.values["at"] == "40" and db.values["earth"] == "10"
    pump = ed.way("c4")
    assert not pump.sized and pump.values["at"] == "16"                # final circuit untouched
    assert sorted(changed) == ["c1", "c2"]
    assert messages == ["DB-2: no connected load, not sized."]
    assert ed.board("SMDB-1").values["incomer_at"] == "100"
    kinds = sorted(c.kind for c in ed.changes())
    assert kinds == ["breaker", "breaker", "cable", "cable"]
    ed.mark_saved()
    assert not ed.way("c1").sized


def test_fed_by_in_the_editor():
    from sld.model import add_fed_by, fed_by_links
    equipment = [EquipmentInfo("SMDB-1", "SMDB-1", fed_by="MDB-9", connected_kw=45.0),
                 EquipmentInfo("SMDB-2", "SMDB-2")]
    links = fed_by_links(dict((e.id, e) for e in equipment), set())
    equipment, circuits = add_fed_by(equipment, [], links)
    ed = Editor(build_schematic(equipment, circuits))
    mdb = next(b for b in ed.boards if b.name == "MDB-9")
    assert mdb.virtual and not ed.fed_by_editable(mdb.id)
    assert ed.fed_by_editable("SMDB-1") and ed.fed_by_editable("SMDB-2")
    assert ed.board_names() == ["MDB-9", "SMDB-1", "SMDB-2"]
    changed, _ = ed.auto_size()                          # sized from the stand-in MDB
    assert ed.way(changed[0]).values["size"] == "25"
    ed.set_board("SMDB-2", "fed_by", "MDB-9")
    kinds = [(c.kind, c.element_id) for c in ed.changes()]
    assert ("fed_by", "SMDB-2") in kinds
    assert not any(e == mdb.id for _, e in kinds)       # nothing written for the stand-in
