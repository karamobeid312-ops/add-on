# -*- coding: utf-8 -*-
from circuitdesc import settings
from circuitdesc.describe import (
    LIGHTING, POWER, wiring_text, CHANGE, FEEDER, NAME, NAME_NUMBER, NO_FIXTURES, NOT_FOUND, NUMBER_NAME, SAME, Circuit,
    describe, fill_unknown, group_loads, headline, label, loads_text, number_text, ordered,
)

BLANK = (u"", u"", u"")


def circuit(labels, old=u"SO", panel=u"PDB-B/1-G", number=u"R1", slot=1, feeder=False):
    return Circuit(None, panel, number, slot, old, labels, feeder)


def test_label_styles():
    assert label(u"012", u"Fire Fighting Pump Room") == u"012 FIRE FIGHTING PUMP ROOM"
    assert label(u"012", u"Pump Room", NAME) == u"PUMP ROOM"
    assert label(u"012", u"Pump Room", NAME_NUMBER) == u"PUMP ROOM 012"
    assert label(u"012", u"Pump  Room ", NUMBER_NAME, upper=False) == u"012 Pump Room"


def test_label_with_a_part_missing():
    assert label(u"", u"Corridor") == u"CORRIDOR"
    assert label(u"B12", u"") == u"B12"
    assert label(u"B12", u"", NAME) == u"B12"
    assert label(None, None) == u""


def test_each_room_once_in_order():
    assert describe([u"101 OFFICE", None, u"102 CORRIDOR", u"101 OFFICE"]) == \
        u"101 OFFICE, 102 CORRIDOR"
    assert describe([None, None]) == u""


def test_status():
    assert circuit([u"012 PUMP ROOM"]).status == CHANGE
    assert circuit([u"012 PUMP ROOM"], old=u"012 PUMP ROOM").status == SAME
    assert circuit([None, None]).status == NOT_FOUND
    assert circuit([]).status == NO_FIXTURES
    assert circuit([], feeder=True).status == FEEDER


def test_fixtures_in_no_room_counted():
    c = circuit([u"101 OFFICE", None, None])
    assert c.status == CHANGE and c.new == u"101 OFFICE" and c.missing == 2


def test_order_as_the_schedule():
    found = ordered([circuit([], panel=u"DB-10", slot=1), circuit([], number=u"Y1", slot=2),
                     circuit([], panel=u"DB-2", slot=3), circuit([], number=u"R1", slot=1)])
    assert [(c.panel, c.number) for c in found] == [
        (u"DB-2", u"R1"), (u"DB-10", u"R1"), (u"PDB-B/1-G", u"R1"), (u"PDB-B/1-G", u"Y1")]


def test_headline():
    assert headline([circuit([u"A"]), circuit([u"B"], panel=u"DB-1"), circuit([])]) == \
        u"2 circuits of 2 boards to describe"


def test_settings_coerced():
    assert settings.coerce("style", NAME) == NAME
    assert settings.coerce("style", "nonsense") == NUMBER_NAME
    assert settings.coerce("upper", "False") is False
    assert settings.coerce("upper", True) is True
    assert settings.coerce("host_spaces", "maybe") is True


def test_number_text():
    assert number_text(36.0) == u"36"
    assert number_text(7.54) == u"7.5"
    assert number_text(None) == u""


def test_load_groups_most_fixtures_first():
    groups, over = group_loads([(u"EXIT", 5), (u"LED 600", 36), (u"LED 600", 36.0),
                                (u"LED 600", 36)])
    assert groups == [(u"LED 600", u"3", u"36"), (u"EXIT", u"1", u"5")] + [BLANK] * 4
    assert not over


def test_same_type_with_another_load_is_its_own_group():
    groups, _ = group_loads([(u"DL", 18), (u"DL", 24)])
    assert groups[:2] == [(u"DL", u"1", u"18"), (u"DL", u"1", u"24")]


def test_load_unknown():
    groups, _ = group_loads([(u"SO", None), (u"SO", None)])
    assert groups[0] == (u"SO", u"2", u"")


def test_more_types_than_slots():
    groups, over = group_loads([(u"T%d" % i, 10) for i in range(8)])
    assert len(groups) == 6 and over


def test_loads_text():
    groups, _ = group_loads([(u"LED", 36), (u"LED", 36), (u"SO", None)])
    assert loads_text(groups) == u"2 x LED (36 W), 1 x SO"


def test_loads_alone_make_a_change():
    fixtures = [(u"LED", 36)]
    old = [BLANK] * 6
    c = Circuit(None, u"DB", u"1", 1, u"101 OFFICE", [u"101 OFFICE"], fixtures=fixtures,
                old_loads=old)
    assert c.status == CHANGE and c.new == c.old and c.loads_changed
    same = Circuit(None, u"DB", u"1", 1, u"101 OFFICE", [u"101 OFFICE"], fixtures=fixtures,
                   old_loads=[(u"LED", u"1", u"36")] + [BLANK] * 5)
    assert same.status == SAME


def test_no_room_keeps_the_description_but_writes_loads():
    c = Circuit(None, u"DB", u"1", 1, u"SO", [None], fixtures=[(u"SO", 200)],
                old_loads=[BLANK] * 6)
    assert c.status == CHANGE and c.new == u"SO" and not c.found


def test_unknown_load_from_the_circuit():
    fixtures = [(u"LED", 36), (u"SO", None), (u"SO", None)]
    assert fill_unknown(fixtures, 436) == [(u"LED", 36), (u"SO", 200), (u"SO", 200)]
    assert fill_unknown(fixtures, None) == fixtures
    assert fill_unknown([(u"A", None), (u"B", None)], 100) == [(u"A", None), (u"B", None)]


WIRING = {u"MCB": u"32", u"Circuit_Wire_Size_mm2": u"", u"Earth_Wire_Size_mm2": u"",
          u"Circuit_Wire_Rating": u"", u"Circuit_Wire_Type": u"", u"Circuit_Type": u""}


def test_power_circuit_gets_the_office_cable():
    c = Circuit(None, u"DB", u"1", 1, u"101 OFFICE", [u"101 OFFICE"], kind=POWER,
                old_wiring=WIRING)
    assert c.status == CHANGE and c.wiring == {
        u"MCB": u"20", u"Circuit_Wire_Size_mm2": u"4", u"Earth_Wire_Size_mm2": u"4",
        u"Circuit_Wire_Rating": u"27.8(5.4)", u"Circuit_Wire_Type": u"SINGLE CORE",
        u"Circuit_Type": u"RAD"}
    again = Circuit(None, u"DB", u"1", 1, u"101 OFFICE", [u"101 OFFICE"], kind=POWER,
                    old_wiring=c.wiring)
    assert again.status == SAME


def test_lighting_circuit_gets_the_lighting_cable():
    c = Circuit(None, u"DB", u"1", 1, u"101 OFFICE", [u"101 OFFICE"], kind=LIGHTING,
                old_wiring=WIRING)
    assert c.wiring == {
        u"MCB": u"16", u"Circuit_Wire_Size_mm2": u"2.5", u"Earth_Wire_Size_mm2": u"2.5",
        u"Circuit_Wire_Rating": u"20.9(4.1)", u"Circuit_Wire_Type": u"SINGLE CORE",
        u"Circuit_Type": u"RAD"}
    assert wiring_text(LIGHTING) == u"MCB 16 A, 2.5 / 2.5 mm\u00b2, 20.9(4.1), SINGLE CORE, RAD"


def test_circuit_of_no_kind_keeps_its_cable():
    c = Circuit(None, u"DB", u"1", 1, u"101 OFFICE", [u"101 OFFICE"], kind=None,
                old_wiring=WIRING)
    assert not c.wiring_changed and c.status == SAME


def test_only_wiring_parameters_on_the_circuit_are_written():
    c = Circuit(None, u"DB", u"1", 1, u"X", [u"X"], kind=POWER,
                old_wiring={u"Circuit_Wire_Type": u""})
    assert c.wiring == {u"Circuit_Wire_Type": u"SINGLE CORE"}
