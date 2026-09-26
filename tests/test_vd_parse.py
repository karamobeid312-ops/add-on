# -*- coding: utf-8 -*-
from vdrop.parse import (Cable, cable, format_number, installation, insulation, length_m,
                         metric_size, number, power_factor, volts)


def test_length():
    assert length_m("175") == 175
    assert length_m("175 m") == 175
    assert length_m("175.5m") == 175.5
    assert length_m("12,5") == 12.5
    assert length_m("17500 mm") == 17.5
    assert abs(length_m("100 ft") - 30.48) < 1e-9
    assert length_m("") is None and length_m("0") is None and length_m("abc") is None


def test_installation():
    assert installation("Cable Tray") == "Cable Tray"
    assert installation("tray") == "Cable Tray"
    assert installation("LADDER") == "Cable Tray"
    assert installation("duct bank") == "Duct Bank"
    assert installation("Ground") == "Ground"
    assert installation("direct buried") == "Ground"
    assert installation("") is None and installation("wall") is None


def test_insulation():
    assert insulation("Cu/XLPE/SWA/PVC") == "XLPE/SWA/PVC"
    assert insulation("XLPE/SWA/LSOH") == "XLPE/SWA/LS0H"
    assert insulation("MICA/XLPE/SWA/LSZH") == "MICA/XLPE/SWA/LS0H"
    assert insulation("Cu/XLPE/AWA/PVC") == "XLPE/SWA/PVC"
    assert insulation("Cu/XLPE/PVC") == "XLPE/PVC"
    assert insulation("PVC") is None


def test_cable():
    assert cable("4Cx16") == Cable(1, 4, 16, None)
    assert cable(u"4Cx16mm² Cu/XLPE/SWA/PVC + 1Cx16mm² Cu/XLPE/PVC") == \
        Cable(1, 4, 16, "XLPE/SWA/PVC")
    assert cable(u"2x(4Cx300mm² Cu/XLPE/SWA/PVC)") == Cable(2, 4, 300, "XLPE/SWA/PVC")
    assert cable("4x4Cx300") == Cable(4, 4, 300, None)
    assert cable("11 x 1C x 630 XLPE/SWA/PVC") == Cable(11, 1, 630, "XLPE/SWA/PVC")
    assert cable(u"4C × 2.5") == Cable(1, 4, 2.5, None)
    assert cable("4C 25") == Cable(1, 4, 25, None)
    assert cable("7 SC 630mm²") is None
    assert cable("") is None and cable(None) is None


def test_metric_size_and_numbers():
    assert metric_size(u"3-16 mm², 1-16 mm², 1-16 mm²") == 16
    assert metric_size("4x2.5mm2") == 2.5
    assert metric_size("3-#12, 1-#12") is None
    assert number("285.12 kW") == 285.12
    assert number("1,5") == 1.5
    assert number("") is None
    assert format_number(4.0) == "4" and format_number(2.5) == "2.5"
    assert format_number(0.12345, 3) == "0.123" and format_number(None) == ""


def test_volts():
    # circuits give Revit's internal unit, voltage types give volts
    assert abs(volts(400 / 0.3048 ** 2) - 400) < 1e-9
    assert abs(volts(120 / 0.3048 ** 2) - 120) < 1e-9
    assert volts(480) == 480 and volts(400) == 400 and volts(230) == 230
    assert volts(0) is None and volts(None) is None and volts(5) is None


def test_power_factor():
    assert power_factor("0.9") == 0.9 and power_factor("0,85") == 0.85
    assert power_factor("90%") == 0.9 and power_factor("90") == 0.9
    assert power_factor("1") == 1.0
    assert power_factor("") is None and power_factor("0") is None and power_factor("150") is None
