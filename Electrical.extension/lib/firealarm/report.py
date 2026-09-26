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
