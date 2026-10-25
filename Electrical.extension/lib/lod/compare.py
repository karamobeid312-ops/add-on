# -*- coding: utf-8 -*-
"""The LOD against the sheets of the Revit model: what is missing on each
side, and which sheet names, revisions and areas differ.

Plain Python (no Revit), so it is tested outside Revit.
"""
from lod.table import full_title, rev_number, rev_text, same_title, sheet_name, text


class Sheet(object):
    """A Revit sheet, as read from the model."""

    def __init__(self, key, number, name, rev=None, area=None, placeholder=False):
        self.key = key                  # element id
        self.number = text(number)
        self.name = text(name)
        self.rev = rev                  # text of the revision parameter, None: no parameter
        self.area = area                # text of the area parameter, None: no parameter
        self.placeholder = placeholder

    def __repr__(self):
        return "Sheet(%r, %r)" % (self.number, self.name)


class Change(object):
    """One value of a Revit sheet that the LOD changes."""

    NAME, REV, AREA = "Sheet name", "Revision", "Area"

    def __init__(self, sheet, drawing, field, old, new):
        self.sheet = sheet
        self.drawing = drawing
        self.field = field
        self.old = old
        self.new = new

    def label(self):
        return u"%s  %s: %s  ->  %s" % (self.sheet.number, self.field, self.old or u"(empty)",
                                         self.new or u"(empty)")


class Comparison(object):
    def __init__(self):
        self.matched = []           # [(drawing, sheet)]
        self.missing = []           # LOD drawings with no sheet
        self.extra = []             # sheets not in the LOD
        self.changes = []           # [Change] to bring the sheets in line with the LOD
        self.duplicates = {}        # {number: [drawings]} repeated in the LOD
        self.no_rev_param = []      # matched sheets without the revision parameter
        self.no_area_param = []     # matched sheets without the area parameter

    def by_field(self, field):
        return [c for c in self.changes if c.field == field]

    def in_step(self):
        return not (self.missing or self.extra or self.changes or self.duplicates)


def same_rev(a, b):
    na, nb = rev_number(a), rev_number(b)
    if na is not None and nb is not None:
        return na == nb
    return text(a).lower() == text(b).lower()


def compare(table, sheets, prefix=u"", use_rev=True, use_area=False):
    """Comparison of an LOD table with the Revit sheets.

    prefix: the part of the LOD titles left out of the sheet names
            ('KEZAD Two Building - '), '' when the names are the full titles.
    use_rev / use_area: compare the revision / area parameters of the sheets.
    """
    result = Comparison()
    result.duplicates = table.duplicates()
    by_number = table.by_number()
    sheets_by_number = {}
    for s in sheets:
        sheets_by_number.setdefault(s.number, s)
    for d in table.drawings:
        if by_number[d.number] is not d:
            continue                        # a repeated number: reported once
        sheet = sheets_by_number.get(d.number)
        if sheet is None:
            result.missing.append(d)
            continue
        result.matched.append((d, sheet))
        wanted = sheet_name(d.title, prefix)
        if not same_title(sheet.name, wanted):
            result.changes.append(Change(sheet, d, Change.NAME, sheet.name, wanted))
        if use_rev and d.rev:
            if sheet.rev is None:
                result.no_rev_param.append(sheet)
            elif not same_rev(sheet.rev, d.rev):
                result.changes.append(Change(sheet, d, Change.REV, sheet.rev, d.rev))
        if use_area and d.area:
            if sheet.area is None:
                result.no_area_param.append(sheet)
            elif text(sheet.area) != d.area:
                result.changes.append(Change(sheet, d, Change.AREA, sheet.area, d.area))
    result.extra = sorted((s for s in sheets if s.number not in by_number),
                          key=lambda s: s.number)
    return result


def title_of(sheet, prefix=u""):
    """LOD title of a Revit sheet."""
    return full_title(sheet.name, prefix)


def rev_of(sheet):
    return rev_text(sheet.rev) if sheet.rev else u""
