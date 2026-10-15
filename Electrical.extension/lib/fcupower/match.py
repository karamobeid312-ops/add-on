# -*- coding: utf-8 -*-
"""Matching the FCUs of the model to the rows of the mechanical schedule.

An FCU's tag is its Comments; it is matched to the schedule rows with the
same tag (case, spaces, dashes and leading zeros ignored), and the served
space of those rows is checked against the room the FCU is in (number and
name). Plain Python (no Revit), so it is tested outside Revit.
"""
from __future__ import division

import re

OK, WARN, BAD = "ok", "warn", "bad"

FULL, PARTIAL, NONE, UNKNOWN = "full", "partial", "none", "unknown"
SAME_WATTS = 0.5                 # W: the value already in the model is kept
TAG_NAME = [u"Comments"]         # the parameter read as the tag (shown in statuses)


def tokens(text):
    """'T1-GF-FCU-01' -> ['T', '1', 'GF', 'FCU', '1']: letters and numbers,
    leading zeros dropped."""
    out = []
    for word in re.findall(r"[A-Za-z]+|\d+", u"%s" % (text or u"")):
        out.append(str(int(word)) if word.isdigit() else word.upper())
    return out


def tag_key(text):
    return u"-".join(tokens(text))


def room_match(schedule_room, number, name):
    """How the schedule's served space agrees with the model's room:
    FULL (number and name), PARTIAL (one of them), NONE, or UNKNOWN when
    the FCU is in no room or the schedule names no space."""
    have = set(tokens(schedule_room))
    num, nam = set(tokens(number)), set(tokens(name))
    if not have or not (num or nam):
        return UNKNOWN
    num_ok = bool(num) and num <= have
    nam_ok = bool(nam) and nam <= have
    if (num_ok or not num) and (nam_ok or not nam):
        return FULL
    if num_ok or nam_ok:
        return PARTIAL
    return NONE


_RANK = {FULL: 3, PARTIAL: 2, UNKNOWN: 1, NONE: 0}


def watts_text(watts):
    if watts is None:
        return u""
    if abs(watts - round(watts)) < 0.05:
        return u"%d" % int(round(watts))
    return (u"%.2f" % watts).rstrip(u"0").rstrip(u".")


class Fcu(object):
    """An FCU of the model, as matched."""

    def __init__(self, key, tag, room_number=u"", room_name=u"", current=None,
                 has_param=True, family=u"", problem=u""):
        self.key = key              # element id
        self.tag = tag or u""
        self.room_number = room_number or u""
        self.room_name = room_name or u""
        self.current = current      # Real_Power_W now, in W (None: empty)
        self.family = family
        # why Real_Power_W cannot be written ('' when it can)
        self.problem = problem or (u"" if has_param else u"No Real_Power_W parameter")
        # results
        self.watts = None
        self.rows = []
        self.state = BAD
        self.status = u""
        self.write = False
        self.can = False            # may be ticked to write (set by the window)
        self.texts = {}             # {parameter name: text}: where the tag may be

    @property
    def room(self):
        return u" ".join(t for t in (self.room_number, self.room_name) if t)


def index_rows(rows):
    """{tag key: [Row]}."""
    out = {}
    for row in rows:
        key = tag_key(row.tag)
        if key:
            out.setdefault(key, []).append(row)
    return out


def _sheets(rows):
    names = []
    for r in rows:
        if r.sheet not in names:
            names.append(r.sheet)
    return u", ".join(names)


def match_one(fcu, by_tag, count_in_model=1):
    """Fill fcu.watts / state / status / write from the schedule rows."""
    fcu.watts, fcu.rows, fcu.write = None, [], False
    if not tag_key(fcu.tag):
        fcu.state, fcu.status = BAD, u"No tag in %s" % TAG_NAME[0]
        return fcu
    rows = by_tag.get(tag_key(fcu.tag), [])
    if not rows:
        fcu.state, fcu.status = BAD, u"Tag not in the schedule"
        return fcu
    levels = [(room_match(r.room, fcu.room_number, fcu.room_name), r) for r in rows]
    best = max(_RANK[level] for level, _ in levels)
    level = next(lv for lv, _ in levels if _RANK[lv] == best)
    chosen = [r for lv, r in levels if _RANK[lv] == best]
    fcu.rows = chosen
    values = []
    for r in chosen:
        if r.watts is not None and all(abs(r.watts - v) > SAME_WATTS for v in values):
            values.append(r.watts)
    if not values:
        fcu.state = BAD
        fcu.status = u"No power in the schedule (%s)" % u", ".join(u"%s" % (r.value if r.value is not None else u"empty") for r in chosen[:2])
        return fcu
    if len(values) > 1:
        fcu.state = BAD
        fcu.status = u"%d schedule rows differ: %s W (%s)" % (
            len(chosen), u" / ".join(watts_text(v) for v in values), _sheets(chosen))
        return fcu
    fcu.watts = values[0]
    notes = []
    state = OK
    if level == NONE:
        state = WARN
        notes.append(u"Room differs: schedule says %s" % chosen[0].room)
    elif level == UNKNOWN:
        state = WARN
        notes.append(u"Room not checked (%s)" % (u"FCU in no room" if not fcu.room
                                                   else u"no space in the schedule"))
    qty = sum(int(r.qty) for r in chosen if r.qty) if all(r.qty for r in chosen) else None
    if qty and count_in_model > qty:
        state = WARN
        notes.append(u"%d in the model, schedule Qty %d" % (count_in_model, qty))
    if fcu.problem:
        fcu.state, fcu.status = BAD, fcu.problem
        return fcu
    if fcu.current is not None and abs(fcu.current - fcu.watts) <= SAME_WATTS:
        fcu.state = state
        fcu.status = u"Already set" + (u" · " + u" · ".join(notes) if notes else u"")
        return fcu
    fcu.state = state
    fcu.write = True
    fcu.status = u" · ".join(notes) if notes else u"Will write"
    return fcu


def match(fcus, rows):
    """Match every FCU; returns the schedule rows no FCU uses."""
    by_tag = index_rows(rows)
    counts = {}
    for fcu in fcus:
        key = tag_key(fcu.tag)
        counts[key] = counts.get(key, 0) + 1
    used = set()
    for fcu in fcus:
        match_one(fcu, by_tag, counts.get(tag_key(fcu.tag), 1))
        for r in fcu.rows:
            used.add(id(r))
    in_model = set(k for k in counts if k)
    return [r for r in rows if id(r) not in used and tag_key(r.tag) not in in_model]


def tag_parameters(fcus, rows):
    """[(parameter name, FCUs with a value, values found in the schedule)]
    of the FCUs' text parameters, best first: the one whose values match
    the most schedule tags, then Comments."""
    keys = set(tag_key(r.tag) for r in rows)
    stats = {}
    for fcu in fcus:
        for name, value in fcu.texts.items():
            filled, found = stats.get(name, (0, 0))
            stats[name] = (filled + (1 if value else 0),
                           found + (1 if value and tag_key(value) in keys else 0))
    stats.setdefault(u"Comments", (0, 0))
    order = sorted(stats.items(), key=lambda kv: (-kv[1][1], kv[0] != u"Comments", -kv[1][0], kv[0]))
    return [(name, filled, found) for name, (filled, found) in order]


def use_tag_parameter(fcus, name):
    TAG_NAME[0] = name
    for fcu in fcus:
        if fcu.texts:
            fcu.tag = fcu.texts.get(name, u"")


def summary(fcus, unused):
    """Counts for the tiles."""
    return {
        "write": sum(1 for f in fcus if f.write),
        "same": sum(1 for f in fcus if f.status.startswith(u"Already set")),
        "check": sum(1 for f in fcus if f.state == WARN),
        "bad": sum(1 for f in fcus if f.state == BAD),
        "unused": len(unused),
        "total": len(fcus),
    }
