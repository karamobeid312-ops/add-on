# -*- coding: utf-8 -*-
from firealarm.report import summarize_auto
from firealarm.room_rules import FLAG, HEAT, NONE, SMOKE, decide, keywords, match, rules_from


def kind(name, area=10.0, height=3.0):
    return decide(name, area, height).kind


def test_heat_rooms():
    for name in ("KITCHEN", "Kitchenette", "PANTRY", "FIRE PUMP ROOM", "GARBAGE ROOM",
                 "REFUSE CHUTE ROOM", "DIESEL GENERATOR ROOM", "BATTERY ROOM",
                 "UPS BATTERY", "DG ROOM", "CLOSED KITCHEN"):
        assert kind(name) == HEAT, name


def test_smoke_rooms_and_default():
    for name in ("BEDROOM", "LIVING ROOM", "CORRIDOR", "LOBBY", "ELECTRICAL ROOM", "LV ROOM",
                 "SERVER ROOM", "LAUNDRY", "STORE", "OFFICE", "MAJLIS", "", "LIFT LOBBY",
                 "BINDERY"):
        assert kind(name) == SMOKE, name


def test_bathrooms_by_area():
    assert kind("TOILET", area=4.0) == NONE
    assert kind("W.C.", area=3.0) == NONE
    assert kind("MALE TOILET", area=12.0) == HEAT
    assert kind("Master Bathroom", area=5.0) == NONE
    assert kind("PUBLIC WASHROOM", area=5.5) == HEAT
    assert decide("TOILET", None, 3.0).kind == NONE


def test_none_and_flag_rooms():
    assert kind("ELECTRICAL SHAFT") == NONE
    assert kind("BASEMENT PARKING") == NONE
    assert kind("BALCONY") == NONE
    assert kind("AHU ROOM") == FLAG
    assert kind("LIFT MACHINE ROOM") == FLAG
    assert "multi-sensor" in decide("LIFT MACHINE ROOM").reason
    assert kind("ATRIUM") == FLAG


def test_high_rooms_flagged():
    d = decide("LOBBY", 200.0, 12.0)
    assert d.kind == FLAG and "beam" in d.reason
    assert "aspirating" in decide("HALL", 900.0, 22.0).reason
    assert decide("KITCHEN", 20.0, 9.9).kind == HEAT


def test_match_whole_words_for_short_keywords():
    assert match("WC-01", ["WC"]) == "WC"
    assert match("WCX", ["WC"]) is None
    assert match("ELEVATOR MACHINE RM", ["ELEVATOR MACHINE"]) == "ELEVATOR MACHINE"
    assert match("MACHINE", ["LIFT MACHINE"]) is None


def test_user_rules():
    rules = rules_from({"rules_heat": "majlis", "rules_none": "", "rules_flag": "",
                        "rules_bath": ""})
    assert decide("MAJLIS", 30, 3, rules).kind == HEAT
    assert decide("KITCHEN", 30, 3, rules).kind == SMOKE
    assert keywords(" a, B ;c\nA") == ["A", "B", "C"]


class Plan(object):
    def __init__(self, label, placed):
        self.label, self.problem = label, ""
        self.placed = list(range(placed))
        self.failed, self.existing, self.spots = [], [], []
        self.layout = None

    def ceiling_heights(self):
        return []


def test_auto_summary():
    rooms = [
        ("101 KITCHEN", decide("KITCHEN", 12, 3), Plan("101 KITCHEN", 2)),
        ("102 OFFICE", decide("OFFICE", 30, 3), Plan("102 OFFICE", 3)),
        ("103 WC", decide("WC", 3, 3), None),
        ("104 AHU", decide("AHU", 20, 3), None),
    ]
    headline, details = summarize_auto(rooms)
    assert headline == ("3 smoke and 2 heat detectors placed in 2 rooms. 1 room needs none. "
                        "1 room to do by hand.")
    assert "101 KITCHEN: 2 detectors (KITCHEN)" in details
    assert "103 WC (WC of 5 m2 or less)" in details
    assert "104 AHU (AHU room: the code wants multi-sensors)" in details
    assert details.index("HEAT") < details.index("SMOKE")
