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


def summarize_riser(run, describe):
    """(headline, details) after FA Riser. run: revit_riser.RiserRun;
    describe(code) -> the symbol's description."""
    riser = run.riser
    loops = riser.loops if riser else []
    devices = sum(l.devices for l in loops)
    off = sum(run.off_loop.values())
    if not loops:
        headline = u"No loops found: draw them with Draw FA Loop first."
        if off:
            headline += u" %d fire alarm device%s found." % (off, "" if off == 1 else "s")
    else:
        floors = len(set(f for l in loops for f in l.floors))
        headline = u"Riser drawn in '%s': %d loop%s, %d device%s on %d floor%s." % (
            run.view_name, len(loops), "" if len(loops) == 1 else "s",
            devices, "" if devices == 1 else "s", floors, "" if floors == 1 else "s")
    if off and loops:
        headline += u" %d device%s on no loop." % (off, "" if off == 1 else "s")
    lines = []
    if run.panel:
        lines.append(u"Main panel: %s on %s" % (run.panel, run.panel_floor))
    else:
        lines.append(u"No fire alarm panel found (a family named FACP, MFACP or ...CONTROL "
                     u"PANEL): the panel is drawn on %s." % run.panel_floor)
    for loop in loops:
        lines.append(u"LOOP#%d: %s, %d device%s" % (
            loop.number, " + ".join(loop.floors), loop.devices, "" if loop.devices == 1 else "s"))
    for warning in (riser.warnings if riser else []):
        lines.append(warning)
    if off:
        lines.append(u"On no loop (no FA Loop line ends at them):")
        for floor, n in sorted(run.off_loop.items()):
            lines.append(u"    %s: %d" % (floor, n))
    if run.two_loops:
        lines.append(u"%d device%s at the ends of two loops' lines, counted on the first." % (
            run.two_loops, "" if run.two_loops == 1 else "s"))
    if run.symbols:
        lines.append(u"Symbols (change them in FA Settings > Riser symbols):")
        for name, code in sorted(run.symbols.items()):
            lines.append(u"    %s -> %s" % (name, describe(code)))
    return headline, "\n".join(lines)
