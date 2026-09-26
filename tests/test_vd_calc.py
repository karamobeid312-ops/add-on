# -*- coding: utf-8 -*-
import math

from sample_vd import ROWS, feeders
from vdrop import tables
from vdrop.calc import BOARD, TRANSFORMER, UPS, Feeder, Settings, cable_text, calculate
from vdrop.parse import Cable

# V.D (%) and cumulative V.D (%) of the office sheet for the sample rows:
# FROM, TO, length, V.D %, cumulative V.D %. The sheet uses 1.73 for the
# square root of 3, so the tool's values are 0.12 % lower.
OFFICE = [
    ('TR', 'LVP-05', 15, 0.1508, 0.1508),
    ('LVP-05', 'ESMDB-WH', 175, 0.9808, 1.1316),
    ('ESMDB-WH', 'ESMDB-1F', 55, 0.9409, 2.0725),
    ('ESMDB-WH', 'ESMDB-2F', 50, 0.8564, 1.988),
    ('ESMDB-WH', 'ESMDB-3F', 55, 0.9456, 2.0772),
    ('ESMDB-WH', 'ESMDB-4F', 60, 1.0277, 2.1593),
    ('ESMDB-WH', 'ESMDB-EQ-1', 60, 0.7791, 1.9107),
    ('ESMDB-WH', 'ESMDB-EQ-2', 60, 0.7043, 1.8359),
    ('ESMDB-WH', 'EDB-Z1-GF', 130, 1.2156, 2.3472),
    ('ESMDB-WH', 'EDB-Z2-GF', 85, 0.7514, 1.883),
    ('ESMDB-WH', 'EDB-Z3-GF', 45, 0.4743, 1.6059),
    ('ESMDB-WH', 'MDF', 20, 0.4909, 1.6225),
    ('ESMDB-WH', 'IT+PSI', 20, 0.3199, 1.4515),
    ('ESMDB-1F', 'EDB-Z1-1F', 85, 0.737, 2.8095),
    ('ESMDB-1F', 'EDB-Z2-1F', 40, 0.3808, 2.4533),
    ('ESMDB-1F', 'EDB-Z3-1F', 10, 0.0918, 2.1643),
    ('ESMDB-2F', 'EDB-Z1-2F', 100, 0.8671, 2.8551),
    ('ESMDB-2F', 'EDB-Z2-2F', 50, 0.476, 2.464),
    ('ESMDB-2F', 'EDB-Z3-2F', 10, 0.0935, 2.0815),
    ('ESMDB-3F', 'EDB-Z1-3F', 100, 0.8671, 2.9442),
    ('ESMDB-3F', 'EDB-Z2-3F', 50, 0.4675, 2.5447),
    ('ESMDB-3F', 'EDB-Z3-3F', 10, 0.0935, 2.1707),
    ('ESMDB-4F', 'EDB-Z1-4F', 100, 0.8671, 3.0264),
    ('ESMDB-4F', 'EDB-Z2-4F', 50, 0.476, 2.6353),
    ('ESMDB-4F', 'EDB-Z3-4F', 10, 0.0935, 2.2528),
    ('ESMDB-EQ-1', 'SEAF-03', 60, 0.8836, 2.7943),
    ('ESMDB-EQ-1', 'SEAF-03', 85, 1.2518, 3.1625),
    ('ESMDB-EQ-1', 'SEAF-03', 95, 1.3991, 3.3098),
    ('ESMDB-EQ-1', 'SEAF-03', 115, 1.6936, 3.6043),
    ('ESMDB-EQ-1', 'SEAF-03', 130, 1.9145, 3.8252),
    ('ESMDB-EQ-1', 'SEAF-03', 150, 1.6066, 3.5173),
    ('ESMDB-EQ-1', 'SEAF-03', 140, 2.0618, 3.9725),
    ('ESMDB-EQ-1', 'SEAF-03', 160, 1.7137, 3.6244),
    ('ESMDB-EQ-2', 'SEAF-03', 180, 1.9279, 3.7638),
    ('ESMDB-EQ-2', 'SEAF-03', 175, 1.8744, 3.7103),
    ('ESMDB-EQ-2', 'SEAF-03', 200, 2.1421, 3.978),
    ('ESMDB-EQ-2', 'SEAF-02', 170, 2.146, 3.9819),
    ('ESMDB-EQ-2', 'SEAF-01', 55, 0.3143, 2.1502),
    ('ESMDB-EQ-2', 'SMAF-01', 85, 0.4588, 2.2947),
    ('ESMDB-EQ-2', 'SMAF-02', 190, 1.559, 3.3949),
    ('TR', 'MDB-02', 15, 0.1073, 0.1073),
    ('MDB-02', 'SMDB-SB-01', 175, 0.3212, 0.4285),
    ('MDB-02', 'SMDB-GF-M2', 115, 117.1946, 117.3019),
    ('SMDB-SB-01', 'PDB-SB', 120, 1.7953, 2.2238),
    ('SMDB-SB-01', 'LDB-SB', 125, 2.0401, 2.4686),
    ('SMDB-SB-01', 'TP-01', 130, 0.4641, 0.8926),
    ('SMDB-SB-01', 'ERV-02', 160, 0.4039, 0.8324),
    ('SMDB-SB-01', 'CWP-01', 155, 0.0761, 0.5046),
    ('SMDB-SB-01', 'AHU-01', 148, 5.0952, 5.5237),
    ('SMDB-SB-01', 'VRF-FAHU-04', 145, 1.2896, 1.7181),
    ('SMDB-SB-01', 'VRF-FAHU-04', 60, 0.0952, 0.5237),
    ('SMDB-SB-01', 'VRF-FAHU-04', 55, 0.1692, 0.5977),
    ('SMDB-SB-01', 'VRF-SR-01', 50, 0.0827, 0.5112),
    ('SMDB-SB-01', 'FOR ERV-01', 55, 0.1147, 0.5432),
    ('SMDB-SB-01', 'FOR EXF-07', 10, 0.0012, 0.4297),
    ('SMDB-SB-01', 'FOR EXF-06', 95, 0.0727, 0.5012),
    ('SMDB-GF-M2', 'SMDB-RF-01', 50, 26.7061, 144.0079),
    ('SMDB-GF-M2', 'SMDB-RF-02', 10, 4.8496, 122.1515),
    ('SMDB-RF-01', 'DB-RF-01', 100, 5.1683, 149.1762),
    ('SMDB-RF-01', 'VRF-L01-04', 50, 2.5706, 146.5785),
    ('SMDB-RF-01', 'VRF-GF-04', 10, 0.5141, 144.5221),
    ('SMDB-RF-01', 'VRF-L02-04', 100, 3.2132, 147.2211),
    ('SMDB-RF-01', 'VRF-FAHU-03-01', 50, 1.6525, 145.6604),
    ('SMDB-RF-01', 'VRF-FAHU-03-02', 10, 0.3305, 144.3384),
    ('SMDB-RF-01', 'VRF-FAHU-03-03', 40, 1.322, 145.3299),
    ('SMDB-RF-01', 'FAHU-03', 100, 2.1268, 146.1348),
    ('SMDB-RF-01', 'ECO-02', 50, 0.4208, 144.4287),
    ('SMDB-RF-01', 'MAHU-02', 10, 0.0459, 144.0538),
    ('SMDB-RF-01', 'VRF-MAHU-02-01', 100, 2.846, 146.8539),
    ('SMDB-RF-01', 'VRF-MAHU-02-02', 50, 1.423, 145.4309),
    ('SMDB-RF-01', 'VRF-MAHU-02-03', 10, 0.2846, 144.2925),
    ('SMDB-RF-01', 'VRF-GF-03', 100, 1.6789, 145.6868),
    ('SMDB-RF-01', 'VRF-L02-03', 45, 1.921, 145.929),
    ('SMDB-RF-01', 'VRF-L01-03', 10, 0.2448, 144.2528),
    ('SMDB-RF-01', 'EXF-02', 10, 0.0153, 144.0232),
    ('SMDB-RF-02', 'FAHU-02', 100, 2.1268, 124.2783),
    ('SMDB-RF-02', 'VRF-FAHU-02-03', 50, 1.6525, 123.804),
    ('SMDB-RF-02', 'VRF-FAHU-02-02', 10, 0.3305, 122.482),
    ('SMDB-RF-02', 'VRF-FAHU-02-01', 100, 3.305, 125.4565),
    ('SMDB-RF-02', 'VRF-GF-02', 50, 1.5377, 123.6893),
    ('SMDB-RF-02', 'VRF-L02-02', 10, 0.5141, 122.6656),
    ('SMDB-RF-02', 'VRF-L01-02', 100, 2.2378, 124.3893),
    ('SMDB-RF-02', 'FAHU-01', 50, 0.9869, 123.1384),
    ('SMDB-RF-02', 'VRF-FAHU-01-01', 10, 0.2846, 122.4361),
    ('SMDB-RF-02', 'VRF-FAHU-01-02', 85, 2.4191, 124.5706),
    ('SMDB-RF-02', 'VRF-FAHU-01-03', 40, 1.1384, 123.2899),
    ('SMDB-RF-02', 'VRF-L02-01', 10, 0.4284, 122.5799),
    ('SMDB-RF-02', 'VRF-GF-01', 85, 3.8367, 125.9882),
    ('SMDB-RF-02', 'VRF-L01-01', 40, 1.371, 123.5225),
    ('SMDB-RF-02', 'VRF-DCWT', 10, 0.1652, 122.3168),
    ('SMDB-RF-02', 'EXF-03', 80, 0.0765, 122.228),
    ('SMDB-RF-02', 'EXF-04', 40, 0.0459, 122.1974),
]


def close(a, b, rel=0.002, abs_tol=0.0005):
    return abs(a - b) <= max(rel * abs(b), abs_tol)


def test_matches_office_sheet():
    result = calculate(feeders())
    rows = sorted(result.rows(), key=lambda r: r.feeder.id)
    assert len(rows) == len(OFFICE) == len(ROWS)
    for row, (src, dst, length, vd, total) in zip(rows, OFFICE):
        assert (row.feeder.source, row.feeder.target, row.feeder.length) == (src, dst, length)
        assert close(row.vd_percent, vd), (src, dst, row.vd_percent, vd)
        assert close(row.total_percent, total), (src, dst, row.total_percent, total)


def test_worked_example():
    # 1.1 LVP-05 -> ESMDB-WH: 285.12 kW, PF 0.85, 175 m of 4 runs 4C 300 mm² in ground
    result = calculate(feeders())
    row = [r for r in result.rows() if r.feeder.target == "ESMDB-WH"][0]
    assert row.number == "1.1"
    assert close(row.kva, 335.435)
    assert close(row.current, 285.12 / 0.85 * 1000 / (math.sqrt(3) * 400))
    assert row.mv_row == 0.185 / 4
    assert row.rating == 590 and row.total_rating == 2360
    assert (row.cb, row.ca, row.cr, row.cg) == (1.0, 0.86, 1.0, 0.85)
    assert close(row.capacity, 2360 * 0.86 * 0.85)
    assert row.breaker_ok and row.cable_ok and row.vd_ok
    assert row.limit == 4.0 and row.status() == "OK"


def test_sections_and_numbers():
    result = calculate(feeders())
    assert [s.title for s in result.sections] == ["LVP-05", "MDB-02"]
    first = result.sections[0].rows
    assert [r.number for r in first[:4]] == ["1", "1.1", "1.1.1", "1.1.1.1"]
    assert (first[0].feeder.source, first[0].feeder.target) == ("TR", "LVP-05")
    assert first[0].limit == 2.5 and first[1].limit == 4.0
    numbers = [r.number for r in result.rows()]
    assert len(numbers) == len(set(numbers))


def test_failures_found_in_office_sheet():
    result = calculate(feeders())
    by_target = dict((r.feeder.target, r) for r in result.rows())
    # typed PASS in the sheet, but 2500 A < 1.1 x 2598 A
    tr = by_target["LVP-05"]
    assert tr.breaker_ok is False and "use breaker 3200A" in tr.suggestions
    # 148 m of 4C 16 mm²: 5.52 % > 4 %, 25 mm² brings it to 3.79 %
    ahu = by_target["AHU-01"]
    assert ahu.vd_ok is False and close(ahu.total_percent, 5.517)
    assert ahu.suggestions == [u"use 4Cx25mm²"]
    # 1019 A on one 4C 10 mm² with a 40 A breaker: the cable carries its
    # breaker, but the breaker and the voltage drop fail; the suggested
    # cable is sized for the suggested breaker
    smdb = by_target["SMDB-GF-M2"]
    assert smdb.breaker_ok is False and smdb.cable_ok is True and smdb.vd_ok is False
    assert smdb.suggestions == ["use breaker 1250A", u"use 2x(4Cx500mm²)"]
    # everything under it is over the limit because of it
    assert "already over the limit upstream" in by_target["DB-RF-01"].suggestions


def feeder(i, src, dst, length=50, kw=10, size=16, runs=1, cores=4, phases=3,
           kind=BOARD, board=False, breaker=None, installation=None):
    return Feeder(id=i, source_id=src, source=src, target=dst,
                  target_id=dst if board else None, length=length, phases=phases,
                  mdl_kw=kw, power_factor=0.85, breaker=breaker, installation=installation,
                  cable=Cable(runs, cores, size) if size else None, source_kind=kind,
                  order=i)


def test_single_phase():
    result = calculate([feeder(0, "DB-1", "LIGHTS", length=30, kw=2, size=4, cores=2,
                               phases=1)])
    row = next(result.rows())
    assert row.voltage == 230
    assert close(row.current, 2 / 0.85 * 1000 / 230)
    assert close(row.mv, 8.3 * 2 / math.sqrt(3))
    assert close(row.vd_volts, row.mv * 30 * row.current / 1000)
    assert close(row.vd_percent, row.vd_volts / 230 * 100)


def test_total_starts_again_after_ups_and_transformer():
    result = calculate([
        feeder(0, "MDB", "SMDB", board=True, length=100),
        feeder(1, "SMDB", "UPS-1", board=True, length=100),
        feeder(2, "UPS-1", "UDB", board=True, length=100, kind=UPS),
        feeder(3, "SMDB", "T-1", board=True, length=100),
        feeder(4, "T-1", "PP-1", board=True, length=100, kind=TRANSFORMER),
    ])
    rows = dict((r.feeder.target, r) for r in result.rows())
    assert close(rows["UPS-1"].total_percent,
                 rows["SMDB"].total_percent + rows["UPS-1"].vd_percent)
    assert rows["UDB"].total_percent == rows["UDB"].vd_percent
    assert rows["PP-1"].total_percent == rows["PP-1"].vd_percent
    assert rows["PP-1"].limit == 2.5 and rows["UDB"].limit == 4.0
    assert [r.number for r in result.sections[0].rows] == \
        ["1.1", "1.1.1", "1.1.1.1", "1.1.2", "1.1.2.1"]


def test_missing_length_and_cable():
    result = calculate([
        feeder(0, "MDB", "SMDB", board=True, length=None),
        feeder(1, "SMDB", "DB-1", length=20),
        feeder(2, "SMDB", "DB-2", length=20, size=None),
    ])
    rows = dict((r.feeder.target, r) for r in result.rows())
    assert rows["SMDB"].vd_percent is None and "no VD Length" in rows["SMDB"].problems
    assert rows["DB-1"].vd_percent is not None and rows["DB-1"].total_percent is None
    assert rows["DB-1"].status() == "INCOMPLETE"
    assert "no total: MDB -> SMDB is incomplete" in rows["DB-1"].problems
    assert "no cable size" in rows["DB-2"].problems
    # nothing to add up without its own length: no chained note
    assert not [p for p in rows["DB-2"].problems if p.startswith("no total")]


def test_reading_notes_are_not_repeated():
    f = feeder(0, "MDB", "DB-1", length=None, size=None)
    f.notes = ["VD Length 'abc' not understood", "wire size '3-#12' is not in mm²"]
    row = next(calculate([f]).rows())
    assert row.problems == f.notes


def test_board_without_incomer_and_feed_loop():
    result = calculate([
        feeder(0, "MDB", "A", board=True),
        feeder(1, "MDB", "B", board=True),
        feeder(2, "X", "Y", board=True),
        feeder(3, "Y", "X", board=True),
    ])
    assert [s.title for s in result.sections] == ["MDB", "X"]
    assert [r.number for r in result.sections[0].rows] == ["1.1", "1.2"]
    assert any("feed loop" in w for w in result.warnings)
    assert len(list(result.rows())) == 4


def test_derating_in_ground():
    settings = Settings(ground_temperature=40, depth=800, soil_resistivity=1.5, grouping=0.7)
    result = calculate([feeder(0, "MDB", "SMDB", size=240, installation="Ground")], settings)
    row = next(result.rows())
    assert (row.ca, row.cb, row.cr, row.cg) == (0.82, 0.96, 0.92, 0.7)
    assert close(row.capacity, 530 * 0.82 * 0.96 * 0.92 * 0.7)
    # cable tray: no depth or soil factor, air temperature
    result = calculate([feeder(0, "MDB", "SMDB", size=240, installation="Cable Tray")], settings)
    row = next(result.rows())
    assert (row.ca, row.cb, row.cr) == (0.96, 1.0, 1.0)


def test_tables():
    assert tables.ampacity("XLPE/SWA/PVC", False, 16, "Cable Tray") == 99
    assert tables.ampacity("XLPE/SWA/LS0H", True, 630, "Duct Bank") == 670
    assert tables.ampacity("XLPE/PVC", False, 10, "Ground") is None
    assert tables.ampacity("PVC/PVC", False, 16, "Ground") is None
    assert tables.mv_per_a_m(False, 300) == 0.185 and tables.mv_per_a_m(True, 16) is None
    # soil resistivity bands follow the table headings
    assert tables.resistivity_factor(2.0, False, "Ground", 16) == 0.84
    assert tables.resistivity_factor(2.0, False, "Ground", 150) == 0.82
    assert tables.resistivity_factor(2.0, False, "Ground", 185) == 0.81
    assert tables.resistivity_factor(2.0, True, "Ground", 300) == 0.8
    assert tables.depth_factor(1000, False, "Cable Tray", 16) == 1.0
    assert tables.next_breaker(61) == 63 and tables.next_breaker(6000) is None


def test_cable_text():
    assert cable_text(1, 4, 16) == u"4Cx16mm²"
    assert cable_text(11, 1, 630) == u"11x(1Cx630mm²)"
    assert cable_text(1, 4, None) == ""
