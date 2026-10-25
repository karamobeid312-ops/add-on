# -*- coding: utf-8 -*-
"""The rows of the LOD Studio window's tabs, worked out from the LOD and the
model as plain data.

Each row is a dict: key, number, c1, c2, c3 (the tab's text columns), status,
state ('ok', 'warn', 'bad' or ''), do (ticked) and can (can be ticked).

Plain Python (no Revit), so it is tested outside Revit.
"""
from lod import keyplan, placeviews
from lod.table import sheet_name

OK, WARN, BAD = "ok", "warn", "bad"


def row(key, number, c1=u"", c2=u"", c3=u"", status=u"", state=u"", do=False, can=False):
    return {"key": u"%s" % key, "number": number or u"", "c1": c1 or u"", "c2": c2 or u"",
            "c3": c3 or u"", "status": status, "state": state, "do": bool(do and can),
            "can": bool(can)}


# ------------------------------------------------------------ 1 Create sheets

def create_rows(table, sheets, prefix=u""):
    """LOD drawings with no sheet in the model, ticked; c1 sheet name, c2 rev,
    c3 area. Repeated numbers are shown once, unticked."""
    existing = set(s.number for s in sheets)
    rows, seen = [], set()
    for d in table.drawings:
        if d.number in existing:
            continue
        if d.number in seen:
            rows.append(row(u"dup:%s:%s" % (d.number, d.row), d.number,
                            sheet_name(d.title, prefix), d.rev, d.area,
                            u"Repeated number in the LOD: skipped", WARN))
            continue
        seen.add(d.number)
        rows.append(row(d.number, d.number, sheet_name(d.title, prefix), d.rev, d.area,
                        u"New sheet", OK, do=True, can=True))
    return rows


# ------------------------------------------------------------ 2 Compare + sync

def change_key(c):
    return u"chg:%s:%s" % (c.sheet.number, c.field)


def compare_rows(result):
    """Every difference: the changes (ticked, written by Sync), then the
    drawings missing in Revit and the sheets not in the LOD (information).
    c1 what, c2 in Revit, c3 in the LOD."""
    rows = []
    for c in result.changes:
        rows.append(row(change_key(c), c.sheet.number, c.field, c.old or u"(empty)",
                        c.new or u"(empty)", u"Will follow the LOD", WARN, do=True, can=True))
    for d in result.missing:
        rows.append(row(u"miss:%s" % d.number, d.number, u"Not in Revit", u"", d.title,
                        u"Create it in tab 1", BAD))
    for s in result.extra:
        rows.append(row(u"extra:%s" % s.number, s.number, u"Not in the LOD", s.name, u"",
                        u"Only in Revit", WARN))
    for s in result.no_rev_param:
        rows.append(row(u"norev:%s" % s.number, s.number, u"Revision", u"(no parameter)", u"",
                        u"Sheet has no revision parameter", WARN))
    return rows


def revision_rows(result, revisions, sheet_revs):
    """Revit revisions (Sheet Issues/Revisions) the matched sheets lack. A
    sheet at LOD Rev. 002 carries every Revit revision numbered up to 002
    (001 and 002), so its title block lists the history; the missing ones
    are ticked to be added.

    revisions: [(revision id, revision number text)] in sequence order
    sheet_revs: {sheet number: set(revision ids on the sheet)}
    """
    from lod.table import rev_number
    numbered, label = [], {}
    for rid, number in revisions:
        label[rid] = number
        n = rev_number(number)
        if n is not None:
            numbered.append((n, rid))
    have = set(n for n, _ in numbered)
    rows, absent = [], {}
    for d, sheet in result.matched:
        n = rev_number(d.rev)
        if n is None:
            continue
        if n not in have:
            absent.setdefault(d.rev, []).append(sheet.number)
            continue
        on = sheet_revs.get(sheet.number) or set()
        add = [rid for m, rid in numbered if m <= n and rid not in on]
        if not add:
            continue
        now = u", ".join(sorted(label.get(r, u"?") for r in on)) or u"(none)"
        rows.append(row(u"rvt:%s:%s" % (sheet.number, u",".join(u"%s" % r for r in add)),
                        sheet.number, u"Revit revision", now, d.rev,
                        u"Will add %s" % u", ".join(label[r] for r in add), WARN,
                        do=True, can=True))
    for rev, numbers in sorted(absent.items()):
        rows.append(row(u"norvt:%s" % rev, u"%d sheets" % len(numbers), u"Revit revision", u"",
                        rev, u"Make revision %s in Revit first" % rev, BAD))
    return rows


def revision_pairs(keys):
    """[(sheet number, revision id)] of the ticked 'Revit revision' rows."""
    pairs = []
    for k in keys:
        if k.startswith(u"rvt:"):
            _, number, rids = k.rsplit(u":", 2)
            pairs.extend((number, int(r)) for r in rids.split(u","))
    return pairs


def compare_counts(result, table):
    return {"drawings": len(table.by_number()), "matched": len(result.matched),
            "missing": len(result.missing), "extra": len(result.extra),
            "changes": len(result.changes)}


# ------------------------------------------------------------ 3 Place views

def view_rows(sheets, views, sheet_numbers, prefix=u""):
    """One row per sheet: the view named like it, c1 sheet name, c2 view.

    sheets: [(sheet id, number, name)]
    views:  [(view id, name, set(sheet ids it is on), legend)]
    sheet_numbers: {sheet id: number} of every sheet.
    Rows to place are ticked; the key is 'sheet id:view id'.
    """
    names = dict((v[0], v[1]) for v in views)
    on = dict((v[0], v[2]) for v in views)
    legend = dict((v[0], v[3]) for v in views)
    found = placeviews.match([(i, n) for i, _, n in sheets],
                             [(v[0], v[1], v[2]) for v in views], prefix)
    unmatched = [(i, n) for i, _, n in sheets if i not in found]
    by_plan = placeviews.match_by_plan(unmatched, [(v[0], v[1], v[2]) for v in views])
    found.update(by_plan)
    free = [(v[0], v[1]) for v in views if not v[2] or v[3]]
    rows = []
    for sid, number, name in sheets:
        ids = found.get(sid)
        if not ids:
            near = placeviews.closest(name, free, prefix)
            if near is None:
                rows.append(row(u"%s:" % sid, number, name, u"", u"", u"No matching view", BAD))
            else:
                rows.append(row(u"%s:%s" % (sid, near[0]), number, name, names[near[0]], u"",
                                u"Close name (%d%%): tick to use" % round(near[1] * 100), WARN,
                                can=True))
            continue
        vid = ids[0]
        where = on.get(vid) or set()
        key = u"%s:%s" % (sid, vid)
        if sid in where:
            rows.append(row(key, number, name, names[vid], u"", u"Already on this sheet", OK))
        elif where and not legend.get(vid):
            others = u", ".join(sorted(sheet_numbers.get(o, u"?") for o in where))
            rows.append(row(key, number, name, names[vid], u"",
                            u"On sheet %s" % others, WARN))
        else:
            extra = u" (%d views match)" % len(ids) if len(ids) > 1 else u""
            if sid in by_plan:
                extra = u" (same plan + floor)" + extra
            rows.append(row(key, number, name, names[vid], u"", u"To place" + extra, WARN,
                            do=True, can=True))
    return rows


# ------------------------------------------------------------ 4 Key plans

def keyplan_rows(sheets, rules, current):
    """One row per sheet: what the rules turn on, c1 sheet name, c2 key plan.

    sheets: [(sheet id, number, name)]
    current: {sheet id: {parameter: value now}} read from the title blocks
             (a parameter the title block lacks is left out).
    Sheets whose key plan would change are ticked.
    """
    rows = []
    for sid, number, name in sheets:
        values = keyplan.values(name, rules)
        now = current.get(sid) or {}
        on = [p for p, v in values if v is True]
        texts = [u"%s = %s" % (p, v) for p, v in values if not isinstance(v, bool)]
        shown = u", ".join(on + texts) or u"-"
        missing = [p for p, v in values if p not in now and (v is True or not isinstance(v, bool))]
        differ = [p for p, v in values if p in now and _differs(now[p], v)]
        if not now:
            rows.append(row(sid, number, name, shown, u"",
                            u"No key plan parameters on this sheet's title block", BAD))
        elif missing:
            rows.append(row(sid, number, name, shown, u"",
                            u"Title block has no %s" % u", ".join(missing), BAD,
                            do=bool(differ), can=True))
        elif differ:
            rows.append(row(sid, number, name, shown, u"",
                            u"Will change %d" % len(differ), WARN, do=True, can=True))
        else:
            rows.append(row(sid, number, name, shown, u"", u"Up to date", OK, can=True))
    return rows


def _differs(now, wanted):
    if isinstance(wanted, bool):
        return bool(now) != wanted
    return (u"%s" % (now or u"")) != (u"%s" % wanted)


def picked(rows):
    return [r["key"] for r in rows if r["do"] and r["can"]]


def tidy_changes(result, keys):
    keys = set(keys)
    return [c for c in result.changes if change_key(c) in keys]

