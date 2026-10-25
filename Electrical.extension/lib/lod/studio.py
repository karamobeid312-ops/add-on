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


def default_rev_map(revisions):
    """{issues back: revision id}, 1 = the newest issue. A sheet at LOD Rev.
    001 is issued for the first time now, so it takes the newest issue only;
    at 002 it was issued once before too, so it takes the newest two (DD and
    CD), and so on (user, 2026-10-25). The issues are the revisions 'Issued
    for ...' (all of them when none says issued), newest = last in sequence."""
    issued = [rid for rid, label in revisions if u"issued" in label.lower()]
    ids = issued or [rid for rid, _ in revisions]
    return dict((i + 1, rid) for i, rid in enumerate(reversed(ids)))


def lod_revs(table):
    """The LOD revision numbers in use, 1 up to the highest."""
    from lod.table import rev_number
    found = [rev_number(d.rev) for d in table.drawings]
    top = max([n for n in found if n is not None] or [0])
    return list(range(1, top + 1))


def revision_rows(result, rev_map, sheet_revs, labels):
    """Revit revisions (Sheet Issues/Revisions) the matched sheets lack. A
    sheet at LOD Rev. n carries the n newest issues (Rev. 001: the newest
    only; 002: the newest and the one before), so its title block lists its
    history; the missing ones are ticked.

    rev_map: {issues back (1 = newest): revision id}
    sheet_revs: {sheet number: set(revision ids on the sheet)}
    labels: {revision id: text shown}
    """
    from lod.table import rev_number, rev_text
    rows, absent = [], {}
    for d, sheet in result.matched:
        n = rev_number(d.rev)
        if not n:
            continue
        unset = [m for m in range(1, n + 1) if rev_map.get(m) is None]
        if unset:
            for m in unset:
                absent.setdefault(m, []).append(sheet.number)
            continue
        on = sheet_revs.get(sheet.number) or set()
        add = [rev_map[m] for m in range(1, n + 1) if rev_map[m] not in on]
        if not add:
            continue
        now = u"%d revision%s" % (len(on), u"" if len(on) == 1 else u"s")
        rows.append(row(u"rvt:%s:%s" % (sheet.number, u",".join(u"%s" % r for r in add)),
                        sheet.number, u"Revit revision", now, d.rev,
                        u"Will add %s" % u", ".join(labels.get(r, u"?").split(u"  (")[0]
                                                   for r in add), WARN,
                        do=True, can=True))
    for m, numbers in sorted(absent.items()):
        rows.append(row(u"norvt:%d" % m, u"%d sheets" % len(numbers), u"Revit revision", u"",
                        u"%s and up" % rev_text(m), u"Pick issue %d back above" % m, BAD))
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


# ------------------------------------------------------------ 5 Scope boxes

# the scope box a plan view takes from its name (user, 2026-10-25), first
# rule that fits wins
SCOPE_RULES = (
    (r"\btower 1\b", u"Building 1"),
    (r"\btower 2\b", u"Building 2"),
    (r"\bpart 1\b", u"Parts GF & 1st 01"),
    (r"\bpart 2\b", u"Parts GF & 1st 02"),
    (r"\boverall\b", u"Overall GF & 1st"),
)


def scope_box_for(view_name):
    """Name of the scope box the view's name asks for, or None."""
    import re
    k = placeviews.key(view_name)
    for pattern, box in SCOPE_RULES:
        if re.search(pattern, k):
            return box
    return None


def scope_rows(views, boxes):
    """One row per plan view whose name asks for a scope box.

    views: [(view id, name, scope box id now or None)]
    boxes: [(scope box id, name)]
    c1 view, c2 scope box now, c3 scope box wanted; key 'view id:box id'.
    """
    by_key, names = {}, {}
    for bid, name in boxes:
        names[bid] = name
        by_key.setdefault(placeviews.key(name), bid)
    rows = []
    for vid, name, now in views:
        want = scope_box_for(name)
        if want is None:
            continue
        now_name = names.get(now, u"") if now else u""
        bid = by_key.get(placeviews.key(want))
        if bid is None:
            rows.append(row(u"%s:" % vid, u"", name, now_name, want,
                            u"No scope box named %s" % want, BAD))
        elif bid == now:
            rows.append(row(u"%s:%s" % (vid, bid), u"", name, now_name, names[bid],
                            u"Up to date", OK, can=True))
        else:
            rows.append(row(u"%s:%s" % (vid, bid), u"", name, now_name or u"(none)", names[bid],
                            u"Will change", WARN, do=True, can=True))
    return rows


def picked(rows):
    return [r["key"] for r in rows if r["do"] and r["can"]]


def tidy_changes(result, keys):
    keys = set(keys)
    return [c for c in result.changes if change_key(c) in keys]

