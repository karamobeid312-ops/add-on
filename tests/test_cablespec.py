# -*- coding: utf-8 -*-
import itertools

from sld.cablespec import ARMOURS, INSULATIONS, MATERIALS, CableSpec, from_vd, parse
from vdrop import parse as vd_parse
from vdrop.parse import Cable


def test_office_text():
    spec = CableSpec(4, 120, earth_size=70)
    assert spec.text() == u"(4X120)mm² CU/XLPE/SWA/PVC +(1X70)mm² CU/PVC(E)"
    assert CableSpec(4, 240, runs=2, armour="").text() == u"2X(4X240)mm² CU/XLPE/PVC"
    assert CableSpec(1, 300, runs=4, armour="AWA").text() == u"4X(1X300)mm² CU/XLPE/AWA/PVC"
    assert CableSpec(4, 2.5).text() == u"(4X2.5)mm² CU/XLPE/SWA/PVC"
    assert CableSpec(4, None).text() == ""


def test_every_choice_round_trips():
    for material, insulation, armour, runs, cores, earth in itertools.product(
            MATERIALS, INSULATIONS, ARMOURS + ("",), (1, 2), (1, 4), (None, 16)):
        spec = CableSpec(cores, 95, runs, material, insulation, armour, "PVC", earth)
        assert parse(spec.text()) == spec, spec.text()


def test_old_and_vd_texts():
    assert parse(u"4Cx16mm² Cu/XLPE/PVC + 1Cx16mm² Cu/XLPE/PVC") == CableSpec(
        4, 16, armour="", earth_size=16)
    assert parse(u"2x(4Cx300mm² Cu/XLPE/SWA/PVC + 1Cx150mm² Cu/XLPE/PVC)") == CableSpec(
        4, 300, 2, earth_size=150)
    assert parse("4x4Cx300 XLPE/SWA/PVC") == CableSpec(4, 300, 4)
    assert parse("4Cx2,5").size == 2.5
    assert parse("") is None and parse("3-#12") is None


def test_voltage_drop_tool_reads_the_office_text():
    text = u"2X(4X240)mm² CU/XLPE/SWA/PVC +(1X120)mm² CU/XLPE/PVC(E)"
    assert vd_parse.cable(text) == Cable(2, 4, 240, "XLPE/SWA/PVC")
    assert CableSpec(4, 16, armour="", earth_size=16).vd_cable() == Cable(1, 4, 16, "XLPE/PVC")
    assert vd_parse.cable(u"4Cx120 Cu/XLPE/PVC + 1Cx70 Cu/XLPE/SWA/PVC").insulation == "XLPE/PVC"


def test_from_vd():
    assert from_vd(Cable(2, 4, 300, "XLPE/SWA/PVC")) == CableSpec(4, 300, 2)
    assert from_vd(None) is None
