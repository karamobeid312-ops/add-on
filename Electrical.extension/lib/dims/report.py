# -*- coding: utf-8 -*-
"""Summary of a dimensioning run (no Revit needed)."""


class Run(object):
    """What happened in one run."""

    def __init__(self, view="", devices=0):
        self.view = view            # name of the view
        self.devices = devices      # devices with a centre plane to dimension to
        self.made = []              # ids of the new dimensions
        self.no_walls = 0           # strings made without some of their walls: Revit refused them
        self.failed = []            # error messages, one per string not made
        self.alone = 0              # devices with nothing to dimension to along one direction
        self.no_wall = 0            # string ends where no wall was found
        self.skew = 0               # string ends at a wall not square to the string
        self.other_no_wall = 0      # strings to the wall on one side: none found on the other
        self.other_skew = 0         # strings to the wall on one side: skew wall on the other
        self.notes = {}             # {(family : type, note): count}: families missing centre planes
        self.hidden = 0             # selected devices not shown in the view
        self.replaced = 0           # old dimensions deleted
        self.helpers = 0            # helper lines drawn through device centres
        self.type_missing = ""      # dimension type of the settings that is not in this model
        self.dims_hidden = False    # the Dimensions category is hidden in the view


def _count(n, word, plural=None):
    return "%d %s" % (n, word if n == 1 else (plural or word + "s"))


def summarize(run):
    """(headline, details)"""
    made = len(run.made)
    if made:
        headline = u"%s added in '%s' for %s." % (
            _count(made, "dimension string"), run.view, _count(run.devices, "device"))
    else:
        headline = u"No dimension strings added in '%s'." % run.view
    if run.replaced:
        headline += " %s replaced." % _count(run.replaced, "old dimension")

    lines = []
    for (label, note), count in sorted(run.notes.items()):
        lines.append(u"%s (%d): %s." % (label, count, note))
    if run.hidden:
        lines.append("%s selected but not shown in this view: skipped."
                     % _count(run.hidden, "device"))
    if run.alone:
        lines.append("%s not dimensioned along one direction: no other device in line and "
                     "no wall square to it found." % _count(run.alone, "device"))
    if run.no_wall:
        lines.append("%s with no wall found, left open (open side, or the wall is hidden in "
                     "3D views or in a link that is not loaded)." % _count(run.no_wall, "string end"))
    if run.skew:
        lines.append("%s at a wall that is not square to the string, left open (round walls, "
                     "or devices not turned with the room)." % _count(run.skew, "string end"))
    if run.other_no_wall:
        lines.append("%s found no wall on one side, so %s to the wall on the other side, which "
                     "may be the far one." % (_count(run.other_no_wall, "string"),
                                              "it goes" if run.other_no_wall == 1 else "they go"))
    if run.other_skew:
        lines.append("%s met a wall that is not square to the devices on one side, so %s to the "
                     "wall on the other side, which may be the far one."
                     % (_count(run.other_skew, "string"),
                        "it goes" if run.other_skew == 1 else "they go"))
    if run.no_walls:
        lines.append("%s made without some of their walls: Revit did not take them (walls "
                     "in a linked model?)." % _count(run.no_walls, "string"))
    for message in sorted(set(run.failed)):
        lines.append(u"%s not made: %s" % (_count(run.failed.count(message), "string"), message))
    if run.type_missing:
        lines.append(u"Dimension type '%s' is not in this model: the model's default type "
                     u"was used (Dim Settings)." % run.type_missing)
    if run.dims_hidden:
        lines.append("Dimensions are hidden in this view: Visibility/Graphics, Annotation "
                     "Categories, Dimensions.")
    if lines:
        headline += " See the notes."
    return headline, "\n".join(lines)
