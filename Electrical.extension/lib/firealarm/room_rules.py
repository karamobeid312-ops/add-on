# -*- coding: utf-8 -*-
"""Smoke or heat detector for a room, from its name, as UAE Fire and Life
Safety Code (2018) Chapter 8, Table 8.14 "Auxiliary Rooms and Spaces"
(no Revit needed).

The rules are lists of name keywords, checked in this order:

1. rooms higher than 10 m: flagged (beam detectors up to 20 m, aspirating
   above, items 18 and 19);
2. FLAG: rooms the code wants other detectors in (multi-sensors in AHU and
   lift machine rooms, items 10 and 12; beam / aspirating in atriums);
3. NONE: no detector (shafts, sprinklered parking, open areas);
4. BATH: toilets and bathrooms, heat when bigger than 5 m2 (public
   bathrooms, item 20), else none;
5. HEAT: kitchens, pantries, pump, garbage, generator and battery rooms
   (items 4, 5, 8, 23, 24, 25, 29);
6. everything else: smoke.

A keyword matches the start of a word in the name ('KITCHEN' matches
'KITCHENETTE'); keywords of 3 letters or less match whole words only
('WC', 'AHU'). Several words must follow each other ('LIFT MACHINE')."""
from __future__ import division

import re

SMOKE, HEAT, NONE, FLAG = "smoke", "heat", "none", "flag"

BEAM_HEIGHT = 10.0      # m, higher rooms need beam detectors (aspirating above 20 m)
ASPIRATING_HEIGHT = 20.0

DEFAULT_RULES = {
    "rules_flag": "AHU, FAHU, LIFT MACHINE, ELEVATOR MACHINE, MACHINE ROOM, LMR, ATRIUM, "
                  "OPERATION, OPERATING",
    "rules_none": "SHAFT, PARKING, CAR PARK, CARPARK, GARAGE, BALCONY, TERRACE, VOID, "
                  "OPEN TO SKY, PLANTER",
    "rules_bath": "TOILET, WC, W C, BATH, WASHROOM, RESTROOM, LAVATORY, SHOWER, POWDER, "
                  "ABLUTION",
    "rules_heat": "KITCHEN, PANTRY, COOKING, PUMP, GARBAGE, REFUSE, TRASH, WASTE, BIN, "
                  "GENERATOR, GENSET, DG, BATTERY, CHARGER",
}
BATH_HEAT_AREA = 5.0    # m2, bigger bathrooms get heat detectors

FLAG_REASONS = {
    "AHU": "AHU room: the code wants multi-sensors",
    "FAHU": "AHU room: the code wants multi-sensors",
    "ATRIUM": "atrium: the code wants beam or aspirating detection",
    "OPERATION": "operation room: the code wants aspirating detection",
    "OPERATING": "operation room: the code wants aspirating detection",
}
LIFT_REASON = "lift machine room: the code wants multi-sensors"


class Decision(object):
    """What a room gets: kind SMOKE / HEAT / NONE / FLAG and why."""

    def __init__(self, kind, reason):
        self.kind = kind
        self.reason = reason

    def __repr__(self):
        return "Decision(%r, %r)" % (self.kind, self.reason)


def keywords(text):
    """'KITCHEN, pantry' -> ['KITCHEN', 'PANTRY']"""
    out = []
    for part in re.split(r"[,;\n]+", text or ""):
        word = normalize(part)
        if word and word not in out:
            out.append(word)
    return out


def normalize(name):
    """Upper case words, anything else a single space: 'Kitchen-01' -> 'KITCHEN 01'."""
    return " ".join(re.sub(r"[^0-9A-Za-z]+", " ", u"%s" % (name or "")).upper().split())


def match(name, keyword_list):
    """The first keyword found in `name`, or None."""
    words = normalize(name).split()
    for keyword in keyword_list:
        parts = keyword.split()
        if not parts:
            continue
        whole = len(keyword.replace(" ", "")) <= 3
        for i in range(len(words) - len(parts) + 1):
            ok = True
            for j, part in enumerate(parts):
                word = words[i + j]
                last = j == len(parts) - 1
                if whole or not last:
                    ok = word == part
                else:
                    ok = word.startswith(part)
                if not ok:
                    break
            if ok:
                return keyword
    return None


def rules_from(values):
    """{'rules_heat': [...], ...} from the settings (defaults where missing)."""
    return dict((key, keywords(values.get(key, default) if values else default))
                for key, default in DEFAULT_RULES.items())


def decide(name, area=None, height=None, rules=None, bath_heat_area=BATH_HEAT_AREA):
    """Decision for a room called `name`; area in m2, height in m (None:
    not known)."""
    rules = rules or rules_from(None)
    if height is not None and height > BEAM_HEIGHT:
        what = "aspirating" if height > ASPIRATING_HEIGHT else "beam"
        return Decision(FLAG, "%.1f m high: the code wants %s detection" % (height, what))
    found = match(name, rules["rules_flag"])
    if found:
        reason = FLAG_REASONS.get(found)
        if reason is None:
            reason = LIFT_REASON if found in ("LIFT MACHINE", "ELEVATOR MACHINE",
                                              "MACHINE ROOM", "LMR") \
                else "%s: place by hand" % found
        return Decision(FLAG, reason)
    found = match(name, rules["rules_none"])
    if found:
        return Decision(NONE, "%s: no detector" % found)
    found = match(name, rules["rules_bath"])
    if found:
        if area is not None and area > bath_heat_area:
            return Decision(HEAT, "%s over %s m2" % (found, _number(bath_heat_area)))
        return Decision(NONE, "%s of %s m2 or less" % (found, _number(bath_heat_area))
                        if area is not None else "%s: no detector" % found)
    found = match(name, rules["rules_heat"])
    if found:
        return Decision(HEAT, found)
    return Decision(SMOKE, "")


def _number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")
