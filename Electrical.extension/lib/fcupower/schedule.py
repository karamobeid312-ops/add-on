# -*- coding: utf-8 -*-
"""The FCU rows of a mechanical schedule sheet: which columns hold the tag,
the served space and the electrical power, the power's unit, and the rows.

Plain Python (no Revit), so it is tested outside Revit.
"""
from __future__ import division

import re

# units of the power column: watts in one of them
UNITS = (u"kW", u"W")
FACTORS = {u"kW": 1000.0, u"W": 1.0}
NO_UNIT = u"?"

HEADER_SCAN = 15                # rows looked at for the header
_EMPTY = (u"", u"-", u"--", u"N/A", u"NA", u"TBC", u"TBA")


def text(value):
    if value is None:
        return u""
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return (u"%s" % value).strip()


def _low(value):
    return u" ".join(text(value).lower().split())


def number(value):
    """The number in a cell (12, '0.25', '1,250 W'), or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    found = re.match(r"^\s*([-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+)\s*([a-zA-Z]*)\s*$", text(value))
    if not found:
        return None
    try:
        return float(found.group(1).replace(u",", u""))
    except ValueError:
        return None


class Column(object):
    def __init__(self, index, label, unit):
        self.index = index
        self.label = label          # header text (all header rows joined)
        self.unit = unit            # kW, W, another unit text or ''

    @property
    def letter(self):
        n, letters = self.index + 1, u""
        while n:
            n, rem = divmod(n - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    @property
    def shown(self):
        """How the column is listed: 'M  Electrical Power (kW)'."""
        name = self.label or u"(no header)"
        return u"%s  %s" % (self.letter, name)


class Row(object):
    def __init__(self, sheet, number, tag, room, value, qty):
        self.sheet = sheet
        self.number = number        # Excel row number
        self.tag = tag
        self.room = room
        self.value = value          # the power cell as written
        self.qty = qty
        self.watts = None

    @property
    def where(self):
        return u"%s row %d" % (self.sheet, self.number)


def _is_tag_header(label):
    low = label.lower()
    return u"tag" in low or u"unit no" in low or u"unit ref" in low or u"fcu no" in low


def header_row(rows):
    """Index of the header row: the first with a tag column, or None."""
    for i, row in enumerate(rows[:HEADER_SCAN]):
        texts = [text(v) for v in row if text(v) and number(v) is None]
        if len(texts) >= 2 and any(_is_tag_header(t) for t in texts):
            return i
    return None


_UNIT_WORDS = ((u"kw", u"kW"), (u"w", u"W"), (u"kva", u"kVA"), (u"va", u"VA"),
               (u"hp", u"HP"), (u"a", u"A"), (u"amps", u"A"), (u"v/ph/hz", u"V/Ph/Hz"))


def unit_of(label):
    """kW, W, ... named in a header ('Electrical Power (kW)', 'kW'), or ''."""
    low = label.lower()
    candidates = re.findall(r"\(([^)]*)\)|\[([^\]]*)\]", low)
    words = [a or b for a, b in candidates] + [low] + low.split()
    for word in words:
        word = word.strip().strip(u".:")
        for raw, unit in _UNIT_WORDS:
            if word == raw:
                return unit
    return u""


def _first_data(rows, header, tag_col):
    """Index of the first data row under the header (the header may run
    over several merged rows, the units row among them)."""
    for i in range(header + 1, min(len(rows), header + 6)):
        row = rows[i]
        if any(number(v) is not None for v in row) and tag_col < len(row) and text(row[tag_col]):
            return i
    return header + 1


def _pick(columns, scores):
    best = None
    for col in columns:
        score = scores(col)
        if score is not None and (best is None or score > best[0]):
            best = (score, col)
    return best[1] if best else None


def _tag_score(col):
    low = col.label.lower()
    if not _is_tag_header(col.label):
        return None
    score = 1
    if u"fcu" in low or u"unit no" in low:
        score += 2
    if re.search(r"odu|outdoor|\biu\b|/", low):
        score -= 2
    return score


def _room_score(col):
    low = col.label.lower()
    for score, word in ((5, u"served space"), (4, u"space"), (3, u"room"), (2, u"location")):
        if word in low:
            return score
    return None


class Sheet(object):
    """One sheet of the schedule, with the columns guessed."""

    def __init__(self, name, rows):
        self.name = name
        self.rows = rows
        self.header = header_row(rows)
        self.columns = []
        self.first = None
        self.tag = self.room = self.power = None
        self.unit = NO_UNIT
        self.qty = None
        if self.header is None:
            return
        width = max(len(r) for r in rows) if rows else 0
        tag_guess = next((i for i, v in enumerate(rows[self.header]) if _is_tag_header(text(v))), 0)
        self.first = _first_data(rows, self.header, tag_guess)
        for col in range(width):
            parts = []
            for r in range(self.header, self.first):
                value = text(rows[r][col]) if col < len(rows[r]) else u""
                if value and value not in parts:
                    parts.append(value)
            label = u" ".join(parts[:1])
            unit_text = u" ".join(parts[1:])
            unit = unit_of(unit_text) or unit_of(label)
            if parts:
                shown = label + (u" (%s)" % unit_text if unit_text else u"")
                self.columns.append(Column(col, shown, unit))
        self.tag = _pick(self.columns, _tag_score)
        self.room = _pick(self.columns, _room_score)
        self.power = _pick(self.columns, self._power_score)
        self.qty = _pick(self.columns, lambda c: 1 if c.label.lower().split()[:1] == [u"qty"]
                         or c.label.lower().startswith(u"quantity") else None)
        self.unit = self.guess_unit(self.power)

    def _values(self, col):
        if col is None or self.first is None:
            return []
        return [r[col.index] for r in self.rows[self.first:] if col.index < len(r)]

    def _power_score(self, col):
        low = col.label.lower()
        if u"power" not in low and u"load" not in low and col.unit not in (u"kW", u"W"):
            return None
        if re.search(r"emergency|cooling|capacity|\btcc\b|\bscc\b|airflow|flow", low):
            return None
        values = [v for v in self._values(col) if text(v) and text(v) not in _EMPTY]
        numeric = sum(1 for v in values if number(v) is not None)
        score = 0
        if values and numeric >= len(values) / 2:
            score += 4
        if col.unit in (u"kW", u"W"):
            score += 1
        if u"power" not in low and u"load" not in low:
            score -= 3
        if low.split(u" (")[0] == u"electrical power":
            score += 2
        if u"indoor" in low:
            score += 1
        if re.search(r"\bdx\b|outdoor|odu|\biu\b", low) and u"input" not in low:
            score -= 2
        return score

    def guess_unit(self, col):
        """kW or W from the header, else NO_UNIT."""
        if col is None:
            return NO_UNIT
        return col.unit if col.unit in UNITS else NO_UNIT

    def column(self, index):
        return next((c for c in self.columns if c.index == index), None)

    @property
    def usable(self):
        return self.header is not None and self.tag is not None

    def fcu_rows(self, tag=None, room=None, power=None, unit=None):
        """[Row] under the header that have a tag, power in watts when
        the unit is known."""
        tag = tag or self.tag
        room = self.room if room is None else room
        power = self.power if power is None else power
        unit = self.unit if unit is None else unit
        if tag is None or self.first is None:
            return []
        factor = FACTORS.get(unit)
        out = []
        for i in range(self.first, len(self.rows)):
            row = self.rows[i]

            def cell(col):
                return row[col.index] if col is not None and col.index < len(row) else None
            tag_text = text(cell(tag))
            if not tag_text or tag_text.upper() in _EMPTY or len(tag_text) > 60:
                continue
            if sum(1 for v in row if text(v)) < 2 or tag_text.lower().startswith(u"note"):
                continue        # a note under the table
            item = Row(self.name, i + 1, tag_text, text(cell(room)), cell(power),
                       number(cell(self.qty)))
            value = number(item.value)
            if value is not None and factor is not None:
                item.watts = round(value * factor, 2)
            out.append(item)
        return out


def sheets(workbook):
    """[Sheet] of [(name, rows)] from xlsxread.read."""
    return [Sheet(name, rows) for name, rows in workbook]
