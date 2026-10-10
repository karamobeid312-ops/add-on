# -*- coding: utf-8 -*-
from circuitdesc import settings
from circuitdesc.describe import (
    CHANGE, FEEDER, NAME, NAME_NUMBER, NO_FIXTURES, NOT_FOUND, NUMBER_NAME, SAME, Circuit,
    describe, headline, label, ordered,
)


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
