# -*- coding: utf-8 -*-
from sld.cables import (cable_from_revit_values, conductor_code, construction,
                        format_cable, insulation_code, parse_metric_sizes)

MM2 = u"mm²"


def test_format_matches_bs_iec_example():
    assert format_cable(4, 4, 1, 4) == u"4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC"


def test_format_variants():
    assert format_cable(2, "2.5") == u"2Cx2.5mm² Cu/XLPE/PVC"
    assert format_cable(4, 95, 1, 50, "Al/XLPE/PVC") == u"4Cx95mm² Al/XLPE/PVC + 1Cx50mm² Al/XLPE/PVC"
    assert format_cable(4, 240, 1, 120, runs=2) == \
        u"2x(4Cx240mm² Cu/XLPE/PVC + 1Cx120mm² Cu/XLPE/PVC)"
    assert format_cable(0, 4) == "" and format_cable(4, "") == ""


def test_parse_metric_sizes():
    assert parse_metric_sizes(u"3-4 mm², 1-4 mm², 1-2.5 mm²") == ["4", "4", "2.5"]
    assert parse_metric_sizes("4x16mm2, 1x16mm2") == ["16", "16"]
    assert parse_metric_sizes("1-6.0 mm") == ["6"]
    assert parse_metric_sizes("3-#12, 1-#12, 1-#12") == []
    assert parse_metric_sizes(None) == []


def test_from_revit_values():
    # 3 phase + neutral + earth
    assert cable_from_revit_values(3, 1, 1, u"3-4 mm², 1-4 mm², 1-4 mm²") == \
        u"4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC"
    # reduced earth size taken from the last size in the text
    assert cable_from_revit_values(3, 1, 1, u"3-35 mm², 1-35 mm², 1-16 mm²") == \
        u"4Cx35mm² Cu/XLPE/PVC + 1Cx16mm² Cu/XLPE/PVC"
    # single phase, no separate earth
    assert cable_from_revit_values(1, 1, 0, u"2-2.5 mm²") == u"2Cx2.5mm² Cu/XLPE/PVC"
    # imperial / unreadable sizes fall back to Revit's text
    assert cable_from_revit_values(3, 1, 1, "3-#12, 1-#12, 1-#12") == "3-#12, 1-#12, 1-#12"


def test_codes():
    assert conductor_code("Copper") == "Cu"
    assert conductor_code("Aluminium") == "Al"
    assert conductor_code("") == "Cu"
    assert insulation_code("THWN") == "XLPE"
    assert insulation_code("PVC 70C") == "PVC"
    assert construction("Al", "XLPE", "PVC") == "Al/XLPE/PVC"
