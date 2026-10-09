# -*- coding: utf-8 -*-
import math

import sample_al_yasat
from sld.geometry import VERTICAL, Drawing, Text, text_box
from sld.layout import (BoardGeom, BoxGeom, LayoutSettings,
                        _cable_label, layout_schematic)
from sld.model import build_schematic


def sample_layout(**kw):
    return layout_schematic(build_schematic(*sample_al_yasat.build()), LayoutSettings(**kw))


def test_floor_bands_bottom_to_top():
    lay = sample_layout()
    labels = [label for label, _ in lay.bands]
    assert labels == ["SUBSTATION", "GROUND FLOOR", "FIRST FLOOR", "SECOND FLOOR", "ROOF FLOOR"]
    ys = [y for _, y in lay.bands]
    assert ys == sorted(ys)


def test_boards_sit_on_their_floor():
    lay = sample_layout()
    floor = dict(lay.bands)
    order = [y for _, y in lay.bands] + [float("inf")]
    def band_range(label):
        y = floor[label]
        return y, order[order.index(y) + 1]
    for g in lay.geoms.values():
        if isinstance(g, BoardGeom) and g.board.is_main:
            lo, hi = band_range("SUBSTATION")
        elif isinstance(g, BoardGeom):
            lo, hi = band_range(g.board.equipment.level_name.upper())
        else:
            lo, hi = band_range(g.way.target.level_name.upper())
        assert lo < g.bottom < hi, g.name


def test_usmdb_stacked_above_gf_board_and_remote_dbs_on_their_floor():
    lay = sample_layout()
    g = dict((x.name, x) for x in lay.geoms.values())
    assert g["USMDB-GF-M"].row == (0, 1) and g["SMDB-GF-M1"].row == (0, 0)
    assert g["USMDB-GF-M"].bottom > g["SMDB-GF-M1"].top
    assert isinstance(g["UDB-FF-01"], BoxGeom) and g["UDB-FF-01"].row[0] == 1
    assert isinstance(g["UDB-SF-02"], BoxGeom) and g["UDB-SF-02"].row[0] == 2
    assert "UDB-GF-01" not in g            # same floor: box drawn above its board


def test_no_overlaps_within_a_row():
    lay = sample_layout()
    geoms = list(lay.geoms.values())
    for i, a in enumerate(geoms):
        for b in geoms[i + 1:]:
            if a.row == b.row:
                assert a.right <= b.left or b.right <= a.left, (a.name, b.name)


def test_feeds_are_orthogonal_and_reach_incomers():
    lay = sample_layout()
    assert len(lay.feeds) == 12
    for f in lay.feeds:
        pts = f.points
        assert pts[0] == (f.source_x(), f.source_y())
        assert abs(pts[-1][0] - f.target.incomer_x) < 1e-6
        assert abs(pts[-1][1] - f.target.feed_y) < 1e-6
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            assert abs(x1 - x2) < 1e-6 or abs(y1 - y2) < 1e-6
            assert y2 >= y1 - 1e-6            # never runs downward


def test_risers_never_cross_boards_on_other_floors():
    lay = sample_layout()
    for f in lay.feeds:
        for (x1, y1), (x2, y2) in zip(f.points, f.points[1:]):
            if abs(x1 - x2) > 1e-6:
                continue  # horizontal jogs run below boards
            lo, hi = min(y1, y2), max(y1, y2)
            for g in lay.geoms.values():
                if g is f.source or g is f.target:
                    continue
                top = g.top + g.content_height()
                crosses = g.left < x1 < g.right and lo < top and hi > g.bottom
                assert not crosses, (f.target.name, g.name)


def test_main_board_details_present():
    lay = sample_layout()
    texts = [t.text for t in lay.drawing.texts]
    for expected in ("MDB-1", "1600AT\n1600AF\nACB", "SPD", "3NO", u"R<1Ω", "TR-01",
                     "FROM TAQA", "MV CABLE FROM TAQA",
                     "1600A,3PH+N+E,50kA FOR 1 SEC\nFORM4-TYPE6\nLOCATION: LV ROOM",
                     u"(7 SC 630mm²", "POWER FACTOR CORRECTION"):
        assert expected in texts, expected
    assert ("250A,3PH+N+E,35kA FOR 1 SEC\nFORM 2b, 18 WAYS\nLOCATION: ELEC. ROOM GF-48"
            "\n@ GROUND FLOOR") in texts
    assert "200AT\n250AF\nMCCB" in texts             # sub-board incomer


def test_utility_setting_and_ratings_toggle():
    lay = sample_layout(utility="DEWA", show_ratings=False)
    texts = [t.text for t in lay.drawing.texts]
    assert "FROM DEWA" in texts and "FROM TAQA" not in texts
    assert not any(t.startswith(u"4Cx16mm²") for t in texts)
    assert any(t.startswith(u"4Cx16mm²") for t in (x.text for x in sample_layout().drawing.texts))
    assert "63AT\n100AF\nMCCB" in texts                # breakers stay either way


def test_board_info_clear_of_busbar():
    lay = sample_layout()
    for g in lay.geoms.values():
        if isinstance(g, BoardGeom) and not g.board.is_main:
            info = next(t for t in lay.drawing.texts if t.text == g.info_text)
            assert text_box(info)[3] < g.bus_y, g.name


def test_load_names_are_vertical():
    lay = sample_layout()
    names = [t for t in lay.drawing.texts if t.text in ("VRF-01", "SPARE", "DB-MEL")]
    assert names and all(t.rotation == VERTICAL for t in names)


def test_cable_label():
    assert _cable_label(u"7 SC 630mm² Cu/XLPE/AWA/PVC") == u"(7 SC 630mm²\nCu/XLPE/AWA/PVC)"
    assert _cable_label(u"4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC") == \
        u"(4Cx4mm² Cu/XLPE/PVC\n+ 1Cx4mm² Cu/XLPE/PVC)"


def test_text_box_rotation():
    t = Text(10.0, 0.0, "ABCD", 2.0, valign="bottom", rotation=VERTICAL)
    x0, y0, x1, y1 = text_box(t)
    assert x1 <= 10.0 + 1e-9 and y0 >= -1e-9 and y1 > y0 + 4


def test_circles_are_split_in_two_arcs():
    d = Drawing()
    d.circle(0, 0, 1)
    assert len(d.arcs) == 2 and abs(d.arcs[1].a1 - 2 * math.pi) < 1e-9


# ---------------------------------------------------------------- overlaps

def _shrink(box, tol):
    return (box[0] + tol, box[1] + tol, box[2] - tol, box[3] - tol)


def _boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _segment_hits_box(x1, y1, x2, y2, box):
    """Liang-Barsky clip of a segment against an axis-aligned box."""
    bx0, by0, bx1, by1 = box
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - bx0), (dx, bx1 - x1), (-dy, y1 - by0), (dy, by1 - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def _arc_points(a, n=24):
    return [a.point(a.a0 + (a.a1 - a.a0) * i / n) for i in range(n + 1)]


def overlaps(drawing, tol=0.15):
    boxes = [(t, _shrink(text_box(t), tol)) for t in drawing.texts]
    problems = []
    for i, (t1, b1) in enumerate(boxes):
        for t2, b2 in boxes[i + 1:]:
            if _boxes_overlap(b1, b2):
                problems.append(("text/text", t1.text, t2.text))
        for l in drawing.lines:
            if _segment_hits_box(l.x1, l.y1, l.x2, l.y2, b1):
                problems.append(("text/line", t1.text, l))
        for a in drawing.arcs:
            if any(b1[0] < x < b1[2] and b1[1] < y < b1[3] for x, y in _arc_points(a)):
                problems.append(("text/arc", t1.text, a))
    return problems


def test_no_overlaps_in_sample():
    for kw in ({}, {"show_ratings": False}):
        problems = overlaps(sample_layout(**kw).drawing)
        assert not problems, problems[:15]


def test_no_overlaps_with_transformer_between_boards():
    from sld.model import CircuitInfo, EquipmentInfo
    equipment = [EquipmentInfo("T-SVC", "T-SVC", part_type="transformer",
                               description=["T-SVC", "TRANSFORMER"]),
                 EquipmentInfo("SWB", "SWB", "Level 1", 0.0, location="ELECTRICAL 101"),
                 EquipmentInfo("T-2A", "T-2A", "Level 1", 0.0, part_type="transformer"),
                 EquipmentInfo("PP-2A", "PP-2A", "Level 2", 4.0, location="ELEC 201"),
                 EquipmentInfo("LP-2A", "LP-2A", "Level 2", 4.0)]
    circuits = [CircuitInfo("c0", "T-SVC", "1", fed_equipment_ids=["SWB"], wire_size="3-#8, 1-#8, 1-#8"),
                CircuitInfo("c1", "SWB", "1,3,5", rating="20 A", poles="3", start_slot=1,
                            wire_size="3-#12, 1-#12, 1-#12", fed_equipment_ids=["T-2A"]),
                CircuitInfo("c2", "SWB", "2,4,6", rating="20 A", poles="3", start_slot=2,
                            wire_size="3-#12, 1-#12, 1-#12", load_name="RTU-1", branch_load_count=1),
                CircuitInfo("c3", "T-2A", "1", fed_equipment_ids=["PP-2A"]),
                CircuitInfo("c4", "PP-2A", "1,3,5", rating="60 A", poles="3", start_slot=1,
                            fed_equipment_ids=["LP-2A"])]
    lay = layout_schematic(build_schematic(equipment, circuits))
    assert not overlaps(lay.drawing), overlaps(lay.drawing)[:15]
    g = dict((x.name, x) for x in lay.geoms.values())
    assert g["PP-2A"].bottom > g["SWB"].top      # above SWB, not beside it
    for f in lay.feeds:
        for (x1, y1), (x2, y2) in zip(f.points, f.points[1:]):
            assert y2 >= y1 - 1e-6                # nothing runs downward


def _texts(drawing):
    return [t.text for t in drawing.texts]


def test_db_boxes_show_connected_and_demand_load():
    lay = sample_layout()
    texts = _texts(lay.drawing)
    g = dict((x.name, x) for x in lay.geoms.values())
    way = next(w for w in g["SMDB-1ST-01"].board.ways if w.name == "LDB-FF-01")
    cl, dl = way.loads()
    assert "CL:%.1f kW" % cl in texts and "DL:%.1f kW" % dl in texts
    box = g["UDB-FF-01"]                           # remote box on its own floor
    assert "CL:%.1f kW" % box.way.loads()[0] in texts


def test_board_has_load_table_with_its_totals():
    lay = sample_layout()
    g = dict((x.name, x) for x in lay.geoms.values())["SMDB-1ST-01"]
    cl, df, dl = g.board.load_totals()
    texts = dict((t.text, t) for t in lay.drawing.texts)
    for label, value in (("CONNECTED LOAD", "%.2fkW" % cl), ("DIVERSITY FACTOR", "%.2f" % df),
                         ("DEMAND LOAD", "%.2fkW" % dl)):
        assert label in texts and value in texts
    table = [texts[v] for v in ("%.2fkW" % cl, "%.2fkW" % dl)]
    for t in table:                               # inside the board, right of the incomer
        assert g.incomer_x < t.x <= g.right and g.bottom < t.y < g.bus_y


def test_lengths_and_vd_along_the_ways():
    lay = sample_layout()
    assert any("V.D:" in t and "L:" in t for t in _texts(lay.drawing))
    lay = sample_layout(show_ratings=False)
    assert not any("V.D:" in t for t in _texts(lay.drawing))
