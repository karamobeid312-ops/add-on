# -*- coding: utf-8 -*-
import pytest

import elecui as ui
from sld import studio
from test_editor import small
from vdrop import settings as vd_settings
from sld import settings as sld_settings


def test_theme_colours():
    assert ui.soft("#E39B12") == "#FFFBEFD9"
    assert ui.argb("#1A9A8A") == "#FF1A9A8A" and ui.argb("FF1A9A8A") == "#FF1A9A8A"
    body = ui.theme_resources("fire")
    assert "#FFD4483F" in body and "__ACCENT" not in body
    assert "<ResourceDictionary" not in body
    with pytest.raises(ValueError):
        ui.window_xaml("<Window/>", "power")


def test_board_state_and_tiles():
    editor = small()
    s = studio.board_summary(editor, "SMDB-1")
    assert s["state"] == "ok" and s["incomer"] == "250 A / 250 AF MCCB"
    assert s["worst_state"] == "ok" and s["worst_vd"].endswith("%")
    lights = editor.ways("SMDB-1")[0]
    editor.set_way(lights.key, "length", "900")
    assert studio.board_state(editor, "SMDB-1") == "bad"
    assert studio.board_summary(editor, "SMDB-1")["worst_state"] == "bad"
    editor.set_way(lights.key, "size", "abc")
    assert studio.board_state(editor, "SMDB-1") == "bad"


def test_vd_table_and_summary():
    editor = small()
    rows = studio.vd_rows(editor)
    assert [r["target"] for r in rows] == ["SMDB-1", "LIGHTS"]
    assert rows[0]["number"] and rows[0]["state"] in ("ok", "warn", "bad")
    assert studio.vd_rows(editor, search="light")[0]["target"] == "LIGHTS"
    s = studio.vd_summary(editor)
    # the SMDB's 250 A breaker is under 1.1 x Ib; LIGHTS has no cable rating
    assert (s["cables"], s["ok"], s["failed"], s["incomplete"]) == ("2", "0", "1", "1")
    assert s["worst"] == "1.87 %" and s["worst_state"] == "ok"
    assert any("breaker" in f for f in s["fixes"])
    assert [r["status"] for r in rows] == ["Failed", "Incomplete"]
    editor.set_way(editor.ways("SMDB-1")[0].key, "length", "900")
    s = studio.vd_summary(editor)
    assert s["failed"] == "2" and s["state"] == "bad" and s["worst_state"] == "bad"
    assert len(studio.vd_rows(editor, problems_only=True)) == 2
    assert studio.vd_tab_header(editor) == (u"Voltage drop  ·  2 failed", "bad")


def test_without_voltage_drop():
    editor = small(vd=False)
    assert studio.vd_rows(editor) == []
    assert studio.vd_summary(editor)["cables"] == u"–"
    assert studio.vd_tab_header(editor)[1] == ""


def test_new_settings_change_the_voltage_drop():
    editor = small()
    before = studio.vd_rows(editor)[1]["total"]
    values = dict(vd_settings.DEFAULTS, limit_total=1.0)
    editor.set_vd_settings(vd_settings.calc_settings(values))
    assert studio.vd_rows(editor)[1]["limit"] == "1"
    assert studio.vd_rows(editor)[1]["total"] == before


def test_settings_form_round_trip():
    form = {}
    sld, vd = dict(sld_settings.DEFAULTS), dict(vd_settings.DEFAULTS)
    for group, key, _, _, kind in studio.SETTINGS:
        value = (sld if group == studio.SLD else vd)[key]
        form[key] = studio.shown(key, value)
        assert studio.read(key, form[key]) == value or key in ("utility", "substation_label")
    new_sld, new_vd, errors = studio.apply_settings(sld, vd, form)
    assert not errors and new_vd == vd and new_sld == sld
    assert not studio.needs_reload(sld, vd, new_sld, new_vd)


def test_settings_form_errors_and_reload():
    sld, vd = dict(sld_settings.DEFAULTS), dict(vd_settings.DEFAULTS)
    _, new_vd, errors = studio.apply_settings(sld, vd, {"power_factor": "1.5",
                                                         "limit_total": "5,5"})
    assert len(errors) == 1 and "Power factor" in errors[0]
    assert new_vd["limit_total"] == 5.5 and new_vd["power_factor"] == vd["power_factor"]
    assert not studio.needs_reload(sld, vd, sld, new_vd)
    _, new_vd, _ = studio.apply_settings(sld, vd, {"load_basis": "TCL - connected load"})
    assert new_vd["load_basis"] == "TCL" and studio.needs_reload(sld, vd, sld, new_vd)
    new_sld, _, _ = studio.apply_settings(sld, vd, {"utility": " taqa ", "show_ratings": False})
    assert new_sld["utility"] == "TAQA" and new_sld["show_ratings"] is False


def _single_pole_board(kws):
    from sld.editor import Editor
    from sld.model import CircuitInfo, EquipmentInfo, build_schematic
    equipment = [EquipmentInfo("DB-1", "SMDB-1")]
    circuits = [CircuitInfo("c%d" % i, "DB-1", str(i + 1), "L%d" % i, rating="10 A", poles="1",
                            start_slot=i + 1, branch_load_count=1, connected_kw=kw)
                for i, kw in enumerate(kws)]
    circuits.append(CircuitInfo("c3p", "DB-1", "20", "AC", rating="32 A", poles="3",
                                start_slot=20, branch_load_count=1, connected_kw=3.0))
    return Editor(build_schematic(equipment, circuits, spares=False), None)


def test_way_phases_follow_way_numbering():
    from sld.model import CircuitInfo, way_phases
    poles = ["1", "1", "3", "1", "1", "1", "1"]
    circuits = [CircuitInfo("c%d" % i, "DB", str(i), poles=p) for i, p in enumerate(poles)]
    assert way_phases(circuits) == ["R", "Y", "RYB", "R", "Y", "B", "R"]
    assert way_phases(circuits, phases=1) == [""] * len(poles)


def test_phase_loads_and_unbalance():
    editor = _single_pole_board([2.0, 1.0, 1.0])     # R 2, Y 1, B 1, plus 1 each from the 3-pole
    ways = editor.ways("DB-1")
    assert [w.phase for w in ways] == ["R", "Y", "B", "RYB"]
    loads = studio.phase_loads(editor, "DB-1")
    assert loads == {"R": 3.0, "Y": 2.0, "B": 2.0}
    assert studio.unbalance(loads) == pytest.approx(28.57, abs=0.01)
    text, sub, state = studio.balance_summary(editor, "DB-1")
    assert text == u"29 %" and sub == u"R 3 · Y 2 · B 2 kW" and state == "bad"
    assert studio.board_state(editor, "DB-1") == "bad"
    studio.set_balance_limits(editor, {"balance_warn": 20.0, "balance_bad": 30.0})
    assert studio.board_state(editor, "DB-1") == "warn"
    assert studio.board_summary(editor, "DB-1")["balance_state"] == "warn"


def test_balanced_board_is_green():
    editor = _single_pole_board([1.0, 1.0, 1.0])
    assert studio.balance_summary(editor, "DB-1")[2] == "ok"
    assert studio.board_state(editor, "DB-1") == "ok"


def test_balance_settings_read_as_numbers():
    sld, vd, errors = studio.apply_settings(sld_settings.DEFAULTS, vd_settings.DEFAULTS,
                                            {"balance_warn": "12,5", "balance_bad": "abc",
                                             "new_view": True})
    assert sld["balance_warn"] == 12.5 and sld["balance_bad"] == 20.0 and sld["new_view"] is True
    assert len(errors) == 1


def test_stored_spares_reach_the_sld_of_a_main_board():
    from sld.model import CircuitInfo, EquipmentInfo, SPARE, build_schematic
    equipment = [EquipmentInfo("MDB", "MDB-01"),
                 EquipmentInfo("SMDB", "SMDB-01", spares="2")]
    circuits = [CircuitInfo("c1", "MDB", "1", rating="40 A", poles="3", start_slot=1,
                            fed_equipment_ids=["SMDB"])]
    sld_settings.apply_spares(equipment, {"MDB-01": ("3", "40AT/100AF MCCB"),
                                          "SMDB-01": ("5", "")})
    assert equipment[0].spares == "3" and equipment[1].spares == "2"   # the panel's own value wins
    mdb = build_schematic(equipment, circuits).roots[0]
    assert sum(1 for w in mdb.ways if w.kind == SPARE) == 3
    assert sld_settings._spares_key("C:\\Jobs\\Al Yasat.rvt") == "spares_C_Jobs_Al_Yasat_rvt"
