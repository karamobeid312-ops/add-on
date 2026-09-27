# -*- coding: utf-8 -*-
"""Summary of a placement run, one line per space (no Revit needed)."""
from __future__ import division


def _heights(values):
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi - lo < 0.005:
        return "ceiling %.2f m" % lo
    return "ceiling %.2f-%.2f m" % (lo, hi)


def space_line(plan):
    if plan.problem:
        return u"%s: skipped, %s" % (plan.label, plan.problem)
    parts = ["%d detector%s" % (len(plan.placed), "" if len(plan.placed) == 1 else "s")]
    heights = _heights(plan.ceiling_heights())
    if heights:
        parts.append(heights)
    on_slab = sum(1 for _, _, hit in plan.spots if hit is not None and not hit.ceiling)
    if on_slab:
        parts.append("%d on the slab (no ceiling found)" % on_slab)
    if plan.layout is not None and plan.layout.uncovered:
        parts.append("CHECK COVERAGE")
    line = u"%s: %s" % (plan.label, ", ".join(parts))
    for message in sorted(set(plan.failed)):
        count = plan.failed.count(message)
        line += u"\n    not placed%s: %s" % (" (%d)" % count if count > 1 else "", message)
    return line


def summarize(plans, kind, replaced=False):
    """(headline, details)"""
    placed = sum(len(p.placed) for p in plans)
    spaces = sum(1 for p in plans if p.placed)
    old = sum(len(p.existing) for p in plans)
    headline = "%d %s detector%s placed in %d space%s." % (
        placed, kind, "" if placed == 1 else "s", spaces, "" if spaces == 1 else "s")
    if old:
        headline += " %d existing one%s %s." % (old, "" if old == 1 else "s",
                                               "replaced" if replaced else "kept")
    problems = sum(1 for p in plans if p.problem or p.failed)
    if problems:
        headline += " %d space%s need%s a look." % (
            problems, "" if problems == 1 else "s", "s" if problems == 1 else "")
    return headline, "\n".join(space_line(p) for p in plans)


def summarize_loops(view_name, results, start_label, start_counted, replaced=0):
    """(headline, details) after Draw FA Loop. results: [LoopResult]."""
    devices = sum(r.devices for r in results)
    headline = u"%d loop%s drawn in '%s': %d device%s." % (
        len(results), "" if len(results) == 1 else "s", view_name,
        devices, "" if devices == 1 else "s")
    if replaced:
        headline += u" %d old loop line%s replaced." % (replaced, "" if replaced == 1 else "s")
    if any(r.failed for r in results):
        headline += u" Some lines could not be drawn."
    lines = [u"Start: %s%s" % (start_label, " (device 1 of loop %d)" % results[0].number
                               if start_counted and results else " (not counted)")]
    for r in results:
        line = u"FA Loop %d: %d device%s, %.0f m of line" % (
            r.number, r.devices, "" if r.devices == 1 else "s", r.length)
        for message in sorted(set(r.failed)):
            count = r.failed.count(message)
            line += u"\n    not drawn%s: %s" % (" (%d)" % count if count > 1 else "", message)
        lines.append(line)
    lines.append(u"Lengths are straight lines in plan from the start and back, "
                 u"without drops and risers.")
    return headline, "\n".join(lines)
