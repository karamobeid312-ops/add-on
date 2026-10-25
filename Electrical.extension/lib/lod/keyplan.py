# -*- coding: utf-8 -*-
"""Key plan switches worked out from a sheet's name.

A key plan is usually Yes/No (visibility) parameters of the title block, or
of a key plan family placed on the sheet, that shade the part of the site the
sheet shows: Tower 1, Tower 2, the podium, Part 1 / Part 2 of a floor, the
parking... Each rule names one parameter and when it is on, from words in the
sheet name:

    {"parameter": "KP Tower 1", "on_if_any": ["Tower 1"]}
    {"parameter": "KP Podium", "on_if_all": ["Main Building"],
                               "off_if_any": ["Tower 1", "Tower 2"]}

A rule with "text" sets a Text parameter instead, with {building}, {tower},
{floor}, {part} and {name} filled from the sheet name:

    {"parameter": "KP Floor", "text": "{floor}"}

Words match whole words, ignoring case, so 'Part 1' does not match 'Part 12'.

Plain Python (no Revit), so it is tested outside Revit.
"""
import json
import re

BUILDINGS = ("Main Building", "Parking Building", "Substation Building", "Service Building",
             "Guard Room Building")

DEFAULT_RULES = [
    {"parameter": "KP Main Building", "on_if_any": ["Main Building"]},
    {"parameter": "KP Podium", "on_if_all": ["Main Building"], "off_if_any": ["Tower 1", "Tower 2"]},
    {"parameter": "KP Tower 1", "on_if_any": ["Tower 1"]},
    {"parameter": "KP Tower 2", "on_if_any": ["Tower 2"]},
    {"parameter": "KP Part 1", "on_if_any": ["Part 1"]},
    {"parameter": "KP Part 2", "on_if_any": ["Part 2"]},
    {"parameter": "KP Parking Building", "on_if_any": ["Parking Building"]},
    {"parameter": "KP Substation Building", "on_if_any": ["Substation Building"]},
    {"parameter": "KP Service Building", "on_if_any": ["Service Building"]},
    {"parameter": "KP Guard Room", "on_if_any": ["Guard Room"]},
    {"parameter": "KP Floor", "text": "{floor}"},
]

_FLOORS = (
    (r"\bground and first floors?\b", u"Ground & First Floor"),
    (r"\boverall ground floor\b|\bground floor\b|\bgf\b", u"Ground Floor"),
    (r"\b(1st|first) floor\b", u"1st Floor"),
    (r"\b(2nd|second) floor\b", u"2nd Floor"),
    (r"\btypical floor\b[^()]*\(([^)]*)\)", None),           # Typical Floor 01 (3rd & 5th)
    (r"\btypical floor\b", u"Typical Floor"),
    (r"\b(\d+)(st|nd|rd|th) floor\b", None),                  # 7th Floor Plan
    (r"\broof\b", u"Roof"),
    (r"\bsetting out\b", u"Site"),
)


class RuleError(Exception):
    pass


def _has(name, word):
    return re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(word.strip()),
                     name, re.IGNORECASE) is not None


def describe(name):
    """{'building', 'tower', 'floor', 'part', 'name'} read from a sheet name;
    '' for what it does not say."""
    name = u"%s" % (name or u"")
    building = next((b for b in BUILDINGS if _has(name, b)), u"")
    tower = re.search(r"\btower\s*(\d+)\b", name, re.IGNORECASE)
    part = re.search(r"\bpart\s*(\d+)\b", name, re.IGNORECASE)
    floor = u""
    for pattern, label in _FLOORS:
        found = re.search(pattern, name, re.IGNORECASE)
        if not found:
            continue
        if label is not None:
            floor = label
        elif "typical" in pattern:
            floor = u"Typical Floor (%s)" % found.group(1).strip()
        else:
            floor = u"%s%s Floor" % (found.group(1), found.group(2).lower())
        break
    return {
        "building": building,
        "tower": u"Tower %s" % tower.group(1) if tower else u"",
        "floor": floor,
        "part": u"Part %s" % part.group(1) if part else u"",
        "name": name,
    }


def check_rules(rules):
    """The rules if they are valid, else RuleError saying what is wrong."""
    if not isinstance(rules, list):
        raise RuleError("The key plan rules must be a list [ ... ] of rules.")
    for i, rule in enumerate(rules):
        where = "Rule %d" % (i + 1)
        if not isinstance(rule, dict):
            raise RuleError("%s is not a { ... } rule." % where)
        if not (u"%s" % rule.get("parameter", "")).strip():
            raise RuleError("%s has no \"parameter\"." % where)
        keys = set(rule) - {"parameter"}
        unknown = keys - {"on_if_any", "on_if_all", "off_if_any", "text"}
        if unknown:
            raise RuleError("%s (%s): unknown key %s." % (where, rule["parameter"],
                                                          ", ".join(sorted(unknown))))
        if not keys:
            raise RuleError("%s (%s): give \"on_if_any\", \"on_if_all\" or \"text\"."
                            % (where, rule["parameter"]))
        for key in ("on_if_any", "on_if_all", "off_if_any"):
            if key in rule and not (isinstance(rule[key], list)
                                    and all(isinstance(w, (type(u""), str)) for w in rule[key])):
                raise RuleError("%s (%s): \"%s\" must be a list of words."
                                % (where, rule["parameter"], key))
        if "text" in rule and ({"on_if_any", "on_if_all", "off_if_any"} & keys):
            raise RuleError("%s (%s): a \"text\" rule cannot also have on/off words."
                            % (where, rule["parameter"]))
    return rules


def parse_rules(raw):
    """Rules from their JSON text ('' gives the default rules)."""
    if raw is None or not (u"%s" % raw).strip():
        return [dict(r) for r in DEFAULT_RULES]
    try:
        rules = json.loads(raw)
    except ValueError as error:
        raise RuleError("The key plan rules are not valid JSON: %s" % error)
    return check_rules(rules)


def dump_rules(rules):
    return json.dumps(rules, indent=2)


def values(name, rules):
    """[(parameter, value)] for a sheet name: True/False for on/off rules,
    text for text rules, in the order of the rules."""
    info = describe(name)
    found = []
    for rule in rules:
        if "text" in rule:
            try:
                value = (u"%s" % rule["text"]).format(**info)
            except (KeyError, IndexError, ValueError):
                value = u"%s" % rule["text"]
            found.append((rule["parameter"], value))
            continue
        on = True
        if "on_if_any" in rule:
            on = any(_has(info["name"], w) for w in rule["on_if_any"])
        if on and "on_if_all" in rule:
            on = all(_has(info["name"], w) for w in rule["on_if_all"])
        if on and "off_if_any" in rule:
            on = not any(_has(info["name"], w) for w in rule["off_if_any"])
        found.append((rule["parameter"], on))
    return found
