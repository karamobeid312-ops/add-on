# -*- coding: utf-8 -*-
"""What Copy Circuits shows (no Revit needed)."""
from copycircuits.plan import ALREADY, BY_NAME, BY_SPOT, NO_PANEL, NONE_FOUND


class Made(object):
    """A circuit made on the target floor."""

    def __init__(self, job, key, panel_error=None):
        self.job = job
        self.key = key                  # the new circuit
        self.panel_error = panel_error  # why its panel refused it, None: on its panel


class LevelResult(object):
    """What was done on one target floor."""

    def __init__(self, level):
        self.level = level
        self.made = []                  # [Made]
        self.failed = []                # [(Job, message)]: Revit refused the circuit
        self.skipped = []               # [Skipped]
        self.wires = {"drawn": 0, "kept": 0, "removed": 0, "no_view": 0, "no_copy": 0,
                      "refused": 0}
        self.wire_views = {}            # plan name -> wires drawn in it
        self.wire_errors = []           # what Revit said when it refused a wire
        self.unwired = []               # target element ids at the ends of wires not drawn
        self.left = []                  # target keys of the circuits' family types left
                                        # with no circuit and no source (new on this floor)
        self.panels = []                # [plan.PanelMatch] of the source floor's panels
        self.by_family = 0              # of the copies, found by family only (other type)
        self.found = 0                  # source elements (not panels) with a copy here
        self.total = 0                  # source elements (not panels)

    def missing(self):
        """Source element keys with no copy on this floor."""
        keys = []
        for item in [m.job for m in self.made] + [j for j, _ in self.failed] + self.skipped:
            for k in item.missing:
                if k not in keys:
                    keys.append(k)
        return keys

    def not_copied(self):
        """Skipped circuits but those of a panel not found (shown with the panels)."""
        return [s for s in self.skipped if s.reason != NO_PANEL]

    def on_panel(self):
        return [m for m in self.made if m.panel_error is None]

    def off_panel(self):
        return [m for m in self.made if m.panel_error is not None]


REASONS = {
    NO_PANEL: "its panel has no copy on this floor (same family type, same spot)",
    NONE_FOUND: "none of its elements has a copy on this floor",
    ALREADY: "its elements here are already on a circuit",
}

MADE_COLUMNS = ["Circuit", "Source", "Elements", "Note"]
PANEL_COLUMNS = ["Panel", "Circuits", "On this floor"]
SKIPPED_COLUMNS = ["Source", "Why not copied"]


def _count(n, word, plural=None):
    return "%d %s" % (n, word if n == 1 else (plural or word + "s"))


def headline(result):
    made = len(result.made)
    if not made:
        return "No circuits made on %s." % result.level
    text = "%s made on %s" % (_count(made, "circuit"), result.level)
    off = len(result.off_panel())
    if off:
        text += ", %d of them not on a panel" % off
    return text + "."


def found_line(result, source_level):
    if not result.total:
        return ""
    text = "%d of %s on %s found on %s (same family type, same spot)." % (
        result.found, _count(result.total, "element"), source_level, result.level)
    if result.by_family:
        text = text[:-2] + "; %d of them of another type of the same family)." % \
            result.by_family
    return text


def _mm(value):
    return "%d mm" % int(round(value))


def panel_found(match):
    if match.how == BY_SPOT:
        return match.found
    if match.how == BY_NAME:
        return u"%s (by name)" % match.found
    looked = (u"no panel named %s, " % match.looked_for) if match.looked_for \
        else u"no floor number in its name to look for it by, "
    if match.nearest is None:
        where = u"no panel of its family type on this floor"
    else:
        where = u"the nearest panel of its family type is %s away" % _mm(match.nearest)
    return u"NOT FOUND: %s%s. Its circuits are not made." % (looked, where)


def panel_row(match):
    return [match.name, match.circuits, panel_found(match)]


def made_note(made):
    job = made.job
    notes = []
    if made.panel_error:
        notes.append(u"not on a panel: %s" % made.panel_error)
    if job.missing:
        notes.append(u"%s with no copy left out" % _count(len(job.missing), "element"))
    if job.already:
        notes.append(u"%s already on a circuit left out" % _count(len(job.already), "element"))
    return u"; ".join(notes)


def made_row(made, link):
    return [link, made.job.circuit.label, len(made.job.elements), made_note(made)]


def skipped_row(skipped):
    return [skipped.circuit.label, REASONS[skipped.reason]]


def wire_lines(result):
    w = result.wires
    lines = []
    if w["drawn"]:
        lines.append("%s drawn, in %s." % (_count(w["drawn"], "wire"), ", ".join(
            "%s (%d)" % (name, n) for name, n in sorted(result.wire_views.items()))))
    if w["removed"]:
        lines.append("%s pasted with the fixtures but not connected, replaced."
                     % _count(w["removed"], "wire"))
    if w["kept"]:
        lines.append("%s already there and connected, kept." % _count(w["kept"], "wire"))
    if w["no_view"]:
        lines.append("%s not drawn: %s has no plan like the one they are in "
                     "(same view type)." % (_count(w["no_view"], "wire"), result.level))
    if w["no_copy"]:
        lines.append("%s not drawn: an element they connect has no copy here."
                     % _count(w["no_copy"], "wire"))
    if w["refused"]:
        lines.append("%s not drawn: Revit refused them (%s)." % (
            _count(w["refused"], "wire"), "; ".join(result.wire_errors) or "no reason given"))
    return lines
