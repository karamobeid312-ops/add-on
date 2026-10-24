# -*- coding: utf-8 -*-
"""Rows of the Floors and Results tabs (no Revit needed)."""
from __future__ import division

OK, WARN, BAD, NONE = "ok", "warn", "bad", ""
TOP_STEPS = (u"mirroring elements and tags", u"board names",
             u"circuits, wires and their tags (all)")


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


def _names(names, most=4):
    names = list(names)
    text = u", ".join(names[:most])
    if len(names) > most:
        text += u" and %d more" % (len(names) - most)
    return text


def _pairs(pairs, most=4):
    return _names([u"%s -> %s" % (a, b) for a, b in pairs], most)


def circuit_rows(floor, circuits):
    """[(values, state, ids)] of a copycircuits LevelResult: Tower 1's
    circuits made again in Tower 2, and their wires."""
    from copycircuits.plan import ALREADY, FALLBACK
    from copycircuits.report import wire_lines
    rows = []

    def add(what, state, ids, item, count=None):
        n = count if count is not None else len(ids)
        if n:
            rows.append(({"floor": floor, "what": what, "count": u"%d" % n, "item": item},
                         state, list(ids)))

    on = circuits.on_panel()
    add(u"Circuits made on Tower 2's boards", OK, [m.key for m in on],
        _names([m.job.circuit.label for m in on]))
    off = circuits.off_panel()
    add(u"Circuits made but not on their board", WARN, [m.key for m in off],
        off[0].panel_error if off else u"")
    add(u"Circuits Revit refused", BAD, [], _names([u"%s: %s" % (j.circuit.label, msg)
                                                    for j, msg in circuits.failed], 2),
        count=len(circuits.failed))
    already = [s for s in circuits.skipped if s.reason == ALREADY]
    add(u"Circuits already in Tower 2", NONE, [], _names([s.circuit.label for s in already]),
        count=len(already))
    other = [s for s in circuits.not_copied() if s.reason != ALREADY]
    add(u"Circuits not made: none of their elements is in Tower 2", WARN, [],
        _names([s.circuit.label for s in other]), count=len(other))
    alone = [m for m in circuits.panels if m.how == FALLBACK]
    add(u"Board with no Tower 2 board: Tower 2's circuits put on it", WARN, [],
        _names([m.name for m in alone]), count=len(alone))
    onto = getattr(circuits, "onto_boards", [])
    add(u"Circuits put back on their board", OK, onto, u"left on no board by an earlier run")
    failed = getattr(circuits, "onto_failed", [])
    add(u"Circuits Revit would not put on their board", BAD, [],
        _names([u"%s: %s" % (label, error) for label, error in failed], 2), count=len(failed))
    lines = wire_lines(circuits)
    if lines:
        w = circuits.wires
        bad = w["refused"] or w["no_view"] or w["no_copy"] or w["no_circuit"]
        add(u"Wires", WARN if bad else OK, circuits.unwired, u" ".join(lines),
            count=w["drawn"] or len(lines))
    return rows


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
    renamed = getattr(result, "renamed", ())
    add(u"Boards named for Tower 2", OK, [], item=_pairs(renamed), count=len(renamed))
    by_name = getattr(result, "by_name", ())
    add(u"Boards found in Tower 2 by name", NONE, [], item=_pairs(by_name), count=len(by_name))
    check = getattr(result, "not_renamed", ())
    add(u"Board names to check by hand", WARN, [], item=_names(check), count=len(check))
    add(u"Already in Tower 2", NONE, [], item=u"same type at the mirrored spot",
        count=result.already)
    add(u"On the mirror line: shared, not mirrored", NONE, [], item=u"", count=result.shared)
    add(u"Leaves Tower 1 (riser, podium...): not mirrored", WARN, result.leaves)
    add(u"In a model group: not mirrored", WARN, result.grouped)
    add(u"Not at its Tower 2 spot: check it", WARN, result.off_spot)
    add(u"No wall at its Tower 2 spot: not placed", BAD, result.no_wall)
    add(u"Revit refused", BAD, result.refused,
        item=u"; ".join(result.errors[:2]) if result.errors else None)
    if getattr(result, "circuits", None) is not None:
        rows.extend(circuit_rows(result.floor, result.circuits))
    seconds = getattr(result, "seconds", None) or {}
    if sum(seconds.values()) >= 1:          # in seconds; circuits / wires are parts of "all"
        add(u"Time taken", NONE, [], item=u", ".join(
            u"%s %d s" % (name, int(round(n))) for name, n in
            sorted(seconds.items(), key=lambda p: -p[1])),
            count=int(round(sum(n for name, n in seconds.items() if name in TOP_STEPS))) or 1)
    if not rows:
        rows.append(({"floor": result.floor, "what": u"Nothing to do", "count": u"",
                      "item": u""}, NONE, []))
    return rows
