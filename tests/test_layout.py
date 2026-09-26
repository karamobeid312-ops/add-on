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
    for expected in ("MDB-1", "ACB", "SPD", "3NO", u"R<1Ω", "TR-01", "FROM TAQA",
                     "MV CABLE FROM TAQA", "FORM4-TYPE6\nLOCATION:LV ROOM",
                     u"(7 SC 630mm²", "POWER FACTOR CORRECTION"):
        assert expected in texts, expected
    assert "FORM 2b, 18 WAYS\nLOCATION: ELEC. ROOM GF-48\n@ GROUND FLOOR" in texts


def test_utility_setting_and_ratings_toggle():
    lay = sample_layout(utility="DEWA", show_ratings=False)
    texts = [t.text for t in lay.drawing.texts]
    assert "FROM DEWA" in texts and "FROM TAQA" not in texts
    assert not any(t.startswith("63A TP") for t in texts)
    assert any(t.startswith("63A TP") for t in (x.text for x in sample_layout().drawing.texts))


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
