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


def summarize_loops(view_name, results, start_label, start_counted, replaced=0, notes=(),
                    kind="detection"):
    """(headline, details) after Draw FA Loop. results: [LoopResult];
    notes: more lines for the end; kind: 'detection' or 'sounder'."""
    devices = sum(r.devices for r in results)
    sounder = kind == "sounder"
    headline = u"%d %sloop%s drawn in '%s': %d device%s." % (
        len(results), "sounder " if sounder else "", "" if len(results) == 1 else "s", view_name,
        devices, "" if devices == 1 else "s")
    if replaced:
        headline += u" %d old loop line%s replaced." % (replaced, "" if replaced == 1 else "s")
    if any(r.failed for r in results):
        headline += u" Some lines could not be drawn."
    lines = [u"Start: %s%s" % (start_label, " (device 1 of loop %d)" % results[0].number
                               if start_counted and results else " (not counted)")]
    for r in results:
        line = u"FA %sLoop %d: %d device%s, %.0f m of line" % (
            "Sounder " if sounder else "", r.number, r.devices, "" if r.devices == 1 else "s",
            r.length)
        for message in sorted(set(r.failed)):
            count = r.failed.count(message)
            line += u"\n    not drawn%s: %s" % (" (%d)" % count if count > 1 else "", message)
        lines.append(line)
    lines.append(u"Lengths are along the lines in plan, from the start and back, "
                 u"without drops and risers.")
    lines.extend(notes)
    return headline, "\n".join(lines)


def summarize_addresses(loops, warnings=(), notes=()):
    """(headline, details) after Address Devices. loops: what was addressed
    (revit_address.AddressedLoop: number, kind, floors, devices, first,
    last); warnings: lines about devices that need a look; notes: more
    lines for the end (parameter, tags)."""
    devices = sum(l.devices for l in loops)
    headline = u"%d device%s addressed on %d loop%s." % (
        devices, "" if devices == 1 else "s", len(loops), "" if len(loops) == 1 else "s")
    if warnings:
        headline += u" Some need a look."
    lines = []
    for l in sorted(loops, key=lambda l: l.number):
        lines.append(u"L%d%s (%s): %d device%s, %s to %s" % (
            l.number, " sounder" if l.kind == "sounder" else "", " + ".join(l.floors),
            l.devices, "" if l.devices == 1 else "s", l.first, l.last))
    lines.extend(warnings)
    lines.extend(notes)
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


def summarize_auto(rooms, replaced=False):
    """(headline, details) after Auto Detectors. rooms: [(label, Decision,
    SpacePlan or None)] in the order the rooms were chosen."""
    count = {"smoke": 0, "heat": 0}
    kinds = {"smoke": [], "heat": [], "none": [], "flag": []}
    for label, decision, plan in rooms:
        kinds[decision.kind].append((label, decision, plan))
        if plan is not None:
            count[decision.kind] += len(plan.placed)
    placed_in = sum(1 for _, _, plan in rooms if plan is not None and plan.placed)
    headline = "%d smoke and %d heat detector%s placed in %d room%s." % (
        count["smoke"], count["heat"], "" if count["heat"] == 1 else "s",
        placed_in, "" if placed_in == 1 else "s")
    if kinds["none"]:
        headline += " %d room%s need%s none." % (
            len(kinds["none"]), "" if len(kinds["none"]) == 1 else "s",
            "s" if len(kinds["none"]) == 1 else "")
    if kinds["flag"]:
        headline += " %d room%s to do by hand." % (
            len(kinds["flag"]), "" if len(kinds["flag"]) == 1 else "s")
    problems = sum(1 for _, _, plan in rooms if plan is not None and (plan.problem or plan.failed))
    if problems:
        headline += " %d room%s need%s a look." % (
            problems, "" if problems == 1 else "s", "s" if problems == 1 else "")
    old = sum(len(plan.existing) for _, _, plan in rooms if plan is not None)
    if old:
        headline += " %d existing detector%s %s." % (old, "" if old == 1 else "s",
                                                    "replaced" if replaced else "kept")
    sections = []
    titles = [("heat", "HEAT (UAE Fire Code Table 8.14)"), ("smoke", "SMOKE"),
              ("flag", "TO DO BY HAND (not placed)"), ("none", "NO DETECTOR")]
    for kind, title in titles:
        if not kinds[kind]:
            continue
        lines = [title]
        for label, decision, plan in kinds[kind]:
            why = u" (%s)" % decision.reason if decision.reason else ""
            if plan is None:
                lines.append(u"%s%s" % (label, why))
            else:
                line = space_line(plan)
                first, _, rest = line.partition("\n")
                lines.append(first + why + ("\n" + rest if rest else ""))
        sections.append("\n".join(lines))
    return headline, "\n\n".join(sections)
