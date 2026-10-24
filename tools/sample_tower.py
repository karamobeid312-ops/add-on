# -*- coding: utf-8 -*-
"""Sample high-rise model: an MDB, a podium SMDB, and tower SMDBs (one per
floor) that a bus bar riser feeds (office SLD 2506 0EE 320). The tower
boards are not circuited from the MDB. Used by the tests and the preview."""
from sld.model import CircuitInfo, EquipmentInfo

FLOORS = ["Ground Floor"] + ["%s Floor" % n for n in
                             ("1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th",
                              "10th", "11th", "12th")]


def build(connected=False, tower_floors=6):
    eq, circuits = [], []
    eq.append(EquipmentInfo("tr", "TR-01", symbol="TRANSFORMER",
                            description=["11/0.4kV", "1000KVA"]))
    eq.append(EquipmentInfo("mdb", "MDB-01", FLOORS[0], 0.0, location="LV ROOM",
                            incomer_rating="1600A", fault_level="50kA",
                            incoming_cable=u"7 SC 630mm² Cu/XLPE/AWA/PVC"))
    circuits.append(CircuitInfo("c-tr", "tr", "1", fed_equipment_ids=["mdb"], poles="3"))
    eq.append(EquipmentInfo("smdb-g", "SMDB-G", FLOORS[0], 0.0, connected_kw=60.0,
                            demand_kw=48.0, upstream_protection="160AT MCCB",
                            fault_level="25kA"))
    circuits.append(CircuitInfo("c-g", "mdb", "1", rating="160", poles="3",
                                fed_equipment_ids=["smdb-g"],
                                cable=u"(4X70)mm² CU/XLPE/SWA/PVC +(1X35)mm² CU/PVC(E)"))
    for i in range(3):
        circuits.append(CircuitInfo("c-gl%d" % i, "smdb-g", str(i + 1), "LIFT %d" % (i + 1),
                                    rating="40", poles="3", connected_kw=10.0,
                                    cable=u"(4X10)mm² CU/XLPE/SWA/PVC"))
    for f in range(1, tower_floors + 1):
        bid = "t%d" % f
        eq.append(EquipmentInfo(bid, "SMDB-T-%d" % f, FLOORS[f], 4.0 * f, location="ELEC. ROOM",
                                incomer_rating="160A", fault_level="25kA",
                                feeder_cable=u"(4X70)mm² CU/XLPE/SWA/PVC +(1X35)mm² CU/PVC(E)",
                                feeder_length=12.0))
        if connected:
            circuits.append(CircuitInfo("c-" + bid, "mdb", str(f + 1), rating="160", poles="3",
                                        fed_equipment_ids=[bid]))
        for j in range(4):
            did = "%s-db%d" % (bid, j)
            eq.append(EquipmentInfo(did, "DB-T%d-%d" % (f, j + 1), FLOORS[f], 4.0 * f,
                                    connected_kw=18.0, demand_kw=14.0))
            circuits.append(CircuitInfo("c-" + did, bid, str(j + 1), rating="63", poles="3",
                                        fed_equipment_ids=[did], connected_kw=18.0,
                                        cable=u"(4X16)mm² CU/XLPE/SWA/PVC +(1X16)mm² CU/PVC(E)"))
    return eq, circuits


def risers(tower_floors=6):
    taps = [dict(board="SMDB-T-%d" % f, rating="", typical="" if f == 1 else "SMDB-T-1")
            for f in range(1, tower_floors + 1)]
    return [dict(name="RISER-1", rating="1000", material="COPPER", fault="50",
                 source="MDB-01", way="", taps=taps)]
