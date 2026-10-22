# -*- coding: utf-8 -*-
"""Rows of the Floors and Results tabs (no Revit needed)."""
from __future__ import division

OK, WARN, BAD, NONE = "ok", "warn", "bad", ""


def floor_row(name, side, picked_tower2):
    """(values, state) of a floor in the Floors tab. side: plan.Side, paired
    when Tower 2 is picked (picked_tower2), else only split by the box."""
    tower1 = len(side.tower1) + len(side.shared)
    skipped = len(side.leaves) + len(side.grouped)
    values = {"floor": name, "tower1": u"%d" % tower1 if tower1 else u"",
              "skipped": u"%d" % skipped if skipped else u""}
    if not picked_tower2:
        values.update(already=u"", todo=u"", status=u"Pick Tower 2 first" if tower1 else u"")
        return values, NONE
    todo = len(side.missing)
    values["already"] = u"%d" % len(side.copies) if side.copies else u""
    values["todo"] = u"%d" % todo if todo else u""
    if not tower1 and not skipped:
        values["status"] = u""
        return values, NONE
    if todo:
        text = u"%d to mirror" % todo
        state = OK
    elif side.tower1:
        text = u"Tower 2 has them all (tick to add missing tags)"
        state = NONE
    else:
        text = u"Nothing to mirror"
        state = NONE
    if skipped:
        text += u", %d skipped" % skipped
        state = WARN if todo or state == NONE else state
    values["status"] = text
    return values, state


def _labels(keys, label_of, most=3):
    """'Pipe : CHW (4), Duct : Rect (2) ...' of the elements."""
    counts = {}
    for k in keys:
        name = label_of(k) or u"(unknown)"
        counts[name] = counts.get(name, 0) + 1
    names = sorted(counts, key=lambda n: (-counts[n], n))
    text = u", ".join(u"%s (%d)" % (n, counts[n]) for n in names[:most])
    if len(names) > most:
        text += u" and %d more types" % (len(names) - most)
    return text


def result_rows(result, label_of, key_of):
    """[(values, state, ids)] of one floor's FloorResult for the Results
    tab. label_of(key) names an element (family : type); key_of(id) is the
    int of an ElementId."""
    rows = []

    def add(what, state, ids, item=None, count=None):
        n = count if count is not None else len(ids)
        if not n:
            return
        rows.append(({"floor": result.floor, "what": what, "count": u"%d" % n,
                      "item": item if item is not None else _labels(
                          [key_of(i) for i in ids], label_of)}, state, list(ids)))

    add(u"Mirrored into Tower 2", OK, result.mirrored)
    add(u"Placed again on Tower 2's walls", OK, [], item=u"of the mirrored",
        count=result.rehosted)
    add(u"Open ends joined", OK, [], item=u"to Tower 2's pipes and ducts and each other",
        count=result.joined)
    add(u"Tags made on Tower 2's copies", OK, [], item=u"same view, mirrored spot",
        count=getattr(result, "tags", 0))
    add(u"Already in Tower 2", NONE, [], item=u"same type at the mirrored spot",
        count=result.already)
    add(u"On the mirror line: shared, not mirrored", NONE, [], item=u"", count=result.shared)
    add(u"Leaves Tower 1 (riser, podium...): not mirrored", WARN, result.leaves)
    add(u"In a model group: not mirrored", WARN, result.grouped)
    add(u"Not at its Tower 2 spot: check it", WARN, result.off_spot)
    add(u"No wall at its Tower 2 spot: not placed", BAD, result.no_wall)
    add(u"Revit refused", BAD, result.refused,
        item=u"; ".join(result.errors[:2]) if result.errors else None)
    if not rows:
        rows.append(({"floor": result.floor, "what": u"Nothing to do", "count": u"",
                      "item": u""}, NONE, []))
    return rows
