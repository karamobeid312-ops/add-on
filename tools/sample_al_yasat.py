# -*- coding: utf-8 -*-
"""Sample model matching drawing 2427 0EE 321 (Al Yasat High School LV
system schematic). Used by the preview tool and the tests, so the layout
can be checked against the office standard without Revit."""
from sld.model import CircuitInfo, EquipmentInfo

GF, FF, SF, RF = "Ground Floor", "First Floor", "Second Floor", "Roof Floor"
ELEV = {GF: 0.0, FF: 4.5, SF: 9.0, RF: 13.5}

TR_DESC = ["11/0.4kV", "1000KVA", "OIL TYPE", "TRANSFORMER"]
MAIN_CABLE = u"7 SC 630mm² Cu/XLPE/AWA/PVC"

# board: (level, location, form, ways, [way specs])
#   ("B", name)   feeder to another board     ("D", name, level)  final DB
#   ("L", name)   equipment via isolator      ("S",)              spare
#   ("P",)        power factor correction     ("U", name)         to UPS
#   ("L1", name)  single-phase load (R/Y/B way)
BOARDS = {
    "MDB-1": (GF, "LV ROOM", "FORM4-TYPE6", 8, [
        ("B", "SMDB-GF-M1"), ("P",), ("L", "EV-01"), ("L", "EV-02"),
        ("L", "EV-03"), ("L", "EV-04"), ("S",), ("S",)]),
    "MDB-2": (GF, "LV ROOM", "FORM4-TYPE6", 4, [
        ("B", "SMDB-BB-01"), ("B", "SMDB-GF-M2"), ("P",), ("S",)]),
    "SMDB-GF-M1": (GF, "ELEC. ROOM GF-48", "FORM 2b", 18, [
        ("B", "SMDB-1ST-01"), ("B", "SMDB-2ND-01"),
        ("D", "LDB-GF-01", GF), ("D", "PDB-GF-01", GF), ("D", "LDB-GF-02", GF),
        ("D", "PDB-GF-02", GF), ("D", "DB-MEL", GF), ("D", "DB-KITCHEN", GF),
        ("D", "DB-AILAB", GF), ("D", "DB-ROBOLAB", GF), ("D", "DB-FOODLAB", GF),
        ("U", "UPS"), ("U", "UPS"), ("S",), ("S",), ("S",)]),
    "USMDB-GF-M": (GF, "UPS ROOM GF-47", "FORM 2b", 8, [
        ("D", "UDB-GF-01", GF), ("D", "UDB-GF-02", GF),
        ("D", "UDB-FF-01", FF), ("D", "UDB-FF-02", FF),
        ("D", "UDB-SF-01", SF), ("D", "UDB-SF-02", SF), ("S",), ("S",)]),
    "SMDB-BB-01": (GF, "ELEC. GF-66", "FORM 2b", 9, [
        ("D", "DB-BB-01", GF), ("D", "DB-BB-02", GF), ("D", "DB-SITE", GF),
        ("L", "ERV-01"), ("L", "ERV-02"), ("L", "AHU-01"), ("L", "VRF-SER"),
        ("L", "VRF-AHU-01"), ("L", "VRF-ERV-01"), ("S",), ("S",), ("S",)]),
    "SMDB-GF-M2": (GF, "ELEC. GF-66", "FORM 2b", 6, [
        ("B", "SMDB-RF-01"), ("B", "SMDB-RF-02"), ("S",), ("S",), ("S",), ("S",)]),
    "SMDB-1ST-01": (FF, "ELEC. FF-53", "FORM 2b", 10, [
        ("D", "LDB-FF-01", FF), ("D", "PDB-FF-01", FF), ("D", "LDB-FF-02", FF),
        ("D", "PDB-FF-02", FF), ("L", "VRF-MAHU-01"), ("L", "ECO-01"),
        ("L", "MAHU-01"), ("D", "DB-ART", FF), ("S",), ("S",)]),
    "SMDB-2ND-01": (SF, "ELEC. SF-55", "FORM 2b", 6, [
        ("D", "LDB-SF-01", SF), ("D", "PDB-SF-01", SF), ("D", "LDB-SF-02", SF),
        ("D", "PDB-SF-02", SF), ("S",), ("S",)]),
    "SMDB-RF-01": (RF, "ELEC. RF-01", "FORM 2b", 18, [
        ("D", "DB-RF-01", RF), ("L", "VRF-FAHU-03-01"), ("L", "VRF-FAHU-03-02"),
        ("L", "VRF-FAHU-03-03"), ("L", "FAHU-03"), ("L", "VRF-01"), ("L", "MAHU-02"),
        ("L", "ECO-02"), ("L1", "HSP-01"), ("L1", "HWR-01"), ("L1", "CWP-01"),
        ("L", "BP-01"), ("L", "VRF-DCWT"), ("L", "VRF-03"), ("L", "VRF-02"),
        ("L", "VRF-06"), ("L", "VRF-05"), ("L", "VRF-04"), ("S",), ("S",)]),
    "SMDB-RF-02": (RF, "ELEC. RF-01", "FORM 2b", 18, [
        ("L", "VRF-07"), ("L", "VRF-08"), ("L", "VRF-EXH-01"), ("L", "VRF-09"),
        ("L", "VRF-10"), ("L", "VRF-11"), ("L", "VRF-12"), ("L", "FAHU-02"),
        ("L", "VRF-FAHU-02-01"), ("L", "VRF-FAHU-02-02"), ("L", "VRF-FAHU-02-03"),
        ("L", "FAHU-01"), ("L", "VRF-FAHU-01-01"), ("L", "VRF-FAHU-01-02"),
        ("L", "VRF-FAHU-01-03"), ("S",), ("S",)]),
}

FEEDER = (u"250 A", "3", u"4Cx120mm² Cu/XLPE/SWA/PVC + 1Cx70mm² Cu/XLPE/PVC")
DB = (u"63 A", "3", u"4Cx16mm² Cu/XLPE/PVC + 1Cx16mm² Cu/XLPE/PVC")
LOAD = (u"32 A", "3", u"4Cx6mm² Cu/XLPE/PVC + 1Cx6mm² Cu/XLPE/PVC")
LOAD_1P = (u"20 A", "1", u"2Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC")


def build():
    """Returns (equipment, circuits) like revit_sld.extract()."""
    eq = {}

    def add(name, level=GF, **kw):
        if name not in eq:
            eq[name] = EquipmentInfo(name, name, level, ELEV[level], **kw)
        return eq[name]

    add("TR-01", GF, part_type="transformer", description=TR_DESC)
    add("TR-02", GF, part_type="transformer", description=TR_DESC)
    add("UPS", GF, family_name="UPS", location="UPS ROOM GF-47")
    for name, (level, location, form, ways, _) in BOARDS.items():
        e = add(name, level)
        e.location, e.form, e.ways = location, form, str(ways)
        if name.startswith("MDB"):
            e.incoming_cable = MAIN_CABLE
            e.mains_rating, e.incomer_rating, e.fault_level = 1600.0, 1600.0, "50 kA"
        else:
            e.mains_rating, e.incomer_rating, e.fault_level = 250.0, "200 A", "35 kA"

    circuits = []

    def circuit(src, slot, poles, rating, cable, load_name="", fed=(), spare=False, branch=0):
        # made-up loads, lengths and voltage drops, varied by slot
        live = not spare and src[:2] != "TR"
        circuits.append(CircuitInfo(
            "%s/%d" % (src, slot), src, str(slot), load_name, rating, poles,
            cable=cable, fed_equipment_ids=list(fed), start_slot=slot,
            is_spare=spare, branch_load_count=branch,
            connected_kw=(2.0 + slot % 7) if live and not fed else None,
            length_m=(10.0, 50.0, 100.0)[slot % 3] if live else None,
            vd_percent=(1.5 + (slot % 9) * 0.27) if live else None))

    circuit("TR-01", 1, "3", "", "", fed=["MDB-1"])
    circuit("TR-02", 1, "3", "", "", fed=["MDB-2"])
    circuit("UPS", 1, "3", u"160 A", FEEDER[2], fed=["USMDB-GF-M"])

    for name, (_, _, _, _, specs) in BOARDS.items():
        slot = 1
        for spec in specs:
            kind = spec[0]
            if kind == "B":
                circuit(name, slot, *FEEDER[1:2], rating=FEEDER[0], cable=FEEDER[2], fed=[spec[1]])
            elif kind == "U":
                circuit(name, slot, "3", u"160 A", FEEDER[2], fed=[spec[1]])
            elif kind == "D":
                db = add(spec[1], spec[2])
                db.connected_kw = 2.0 + (slot % 11) * 1.3
                db.demand_kw = round(db.connected_kw * 0.85, 1)
                circuit(name, slot, "3", DB[0], DB[2], fed=[spec[1]])
            elif kind == "L":
                circuit(name, slot, "3", LOAD[0], LOAD[2], load_name=spec[1], branch=1)
            elif kind == "L1":
                circuit(name, slot, "1", LOAD_1P[0], LOAD_1P[2], load_name=spec[1], branch=1)
                slot += 1
                continue
            elif kind == "P":
                circuit(name, slot, "3", u"400 A", "", load_name="PFC", branch=1)
            elif kind == "S":
                circuit(name, slot, "3", "", "", spare=True)
            slot += 3
    return list(eq.values()), circuits
