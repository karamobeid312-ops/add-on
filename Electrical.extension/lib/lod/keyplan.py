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

A rule with "otherwise" is on only when no other on/off rule is on:

    {"parameter": "No keyplan", "otherwise": true}

Words match whole words, ignoring case, so 'Part 1' does not match 'Part 12'.

Plain Python (no Revit), so it is tested outside Revit.
"""
import json
import re

BUILDINGS = ("Main Building", "Parking Building", "Substation Building", "Service Building",
             "Guard Room Building")

TOWERS = ["Tower 1", "Tower 2"]
PART_1 = ["Part 1", "Part 01"]
PART_2 = ["Part 2", "Part 02"]
GROUND = ["Ground Floor", "GF"]
FIRST = ["First Floor", "1st Floor", "FF"]

# The KEZAD title block: one Yes/No parameter per key plan picture. Exactly one
# picture is on for a sheet; 'No keyplan' is on when none of the others is.
# 'North Sign' has no rule, so it is left as it is.
DEFAULT_RULES = [
    {"parameter": "Building 1", "on_if_any": ["Tower 1"]},
    {"parameter": "Building 2", "on_if_any": ["Tower 2"]},
    {"parameter": "Ground Overall", "on_if_any": GROUND, "on_if_all": ["Main Building"],
     "off_if_any": TOWERS + PART_1 + PART_2 + FIRST},
    {"parameter": "First Overall", "on_if_any": FIRST, "on_if_all": ["Main Building"],
     "off_if_any": TOWERS + PART_1 + PART_2 + GROUND},
    {"parameter": "GF & FF Part 01", "on_if_any": PART_1, "on_if_all": ["Main Building"],
     "off_if_any": TOWERS},
    {"parameter": "GF & FF Part 02", "on_if_any": PART_2, "on_if_all": ["Main Building"],
     "off_if_any": TOWERS},
    {"parameter": "Parking Overall", "on_if_any": ["Parking Building", "Parking"],
     "off_if_any": PART_1 + PART_2},
    {"parameter": "Parking Part 01", "on_if_any": PART_1, "on_if_all": ["Parking"]},
    {"parameter": "Parking Part 02", "on_if_any": PART_2, "on_if_all": ["Parking"]},
    {"parameter": "Service Building", "on_if_any": ["Service Building"]},
    {"parameter": "Substation", "on_if_any": ["Substation"]},
    {"parameter": "Guard Room 1", "on_if_any": ["Guard Room 1", "Guard Room 01"]},
    {"parameter": "Guard Room 2", "on_if_any": ["Guard Room 2", "Guard Room 02"]},
    {"parameter": "Site Overall", "on_if_any": ["Site", "Setting Out", "External", "Overall Site"],
     "off_if_any": ["Main Building", "Parking", "Service Building", "Substation", "Guard Room"]},
    {"parameter": "Section AA", "on_if_any": ["Section AA", "Section A-A"]},
    {"parameter": "Section BB", "on_if_any": ["Section BB", "Section B-B"]},
    {"parameter": "Wall Section", "on_if_any": ["Wall Section"]},
    {"parameter": "Section 01", "on_if_any": ["Section 01", "Section 1"]},
    {"parameter": "Section 02", "on_if_any": ["Section 02", "Section 2"]},
    {"parameter": "Section 03", "on_if_any": ["Section 03", "Section 3"]},
    {"parameter": "Section 04", "on_if_any": ["Section 04", "Section 4"]},
    {"parameter": "Section 05", "on_if_any": ["Section 05", "Section 5"]},
    {"parameter": "No keyplan", "otherwise": True},
]

# The first default rules (KP Tower 1, KP Podium...): saved copies of them are
# read as the new defaults, since no title block has these names.
_OLD_DEFAULT_PARAMETERS = [
    "KP Main Building", "KP Podium", "KP Tower 1", "KP Tower 2", "KP Part 1", "KP Part 2",
    "KP Parking Building", "KP Substation Building", "KP Service Building", "KP Guard Room",
    "KP Floor",
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
        unknown = keys - {"on_if_any", "on_if_all", "off_if_any", "text", "otherwise"}
        if unknown:
            raise RuleError("%s (%s): unknown key %s." % (where, rule["parameter"],
                                                          ", ".join(sorted(unknown))))
        if not keys:
            raise RuleError("%s (%s): give \"on_if_any\", \"on_if_all\", \"text\" or "
                            "\"otherwise\"."
                            % (where, rule["parameter"]))
        for key in ("on_if_any", "on_if_all", "off_if_any"):
            if key in rule and not (isinstance(rule[key], list)
                                    and all(isinstance(w, (type(u""), str)) for w in rule[key])):
                raise RuleError("%s (%s): \"%s\" must be a list of words."
                                % (where, rule["parameter"], key))
        if "text" in rule and ({"on_if_any", "on_if_all", "off_if_any"} & keys):
            raise RuleError("%s (%s): a \"text\" rule cannot also have on/off words."
                            % (where, rule["parameter"]))
        if "otherwise" in rule and len(keys) > 1:
            raise RuleError("%s (%s): an \"otherwise\" rule cannot have other keys."
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
    rules = check_rules(rules)
    if [r.get("parameter") for r in rules] == _OLD_DEFAULT_PARAMETERS:
        return [dict(r) for r in DEFAULT_RULES]
    return rules


def dump_rules(rules):
    return json.dumps(rules, indent=2)


def values(name, rules):
    """[(parameter, value)] for a sheet name: True/False for on/off rules,
    text for text rules, in the order of the rules. An "otherwise" rule is on
    when no on/off rule is."""
    info = describe(name)
    found = []
    for rule in rules:
        if "otherwise" in rule:
            found.append((rule["parameter"], None))
            continue
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
    any_on = any(v is True for _, v in found)
    return [(p, (not any_on) if v is None else v) for p, v in found]
