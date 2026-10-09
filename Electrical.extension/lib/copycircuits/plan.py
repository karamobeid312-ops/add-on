# -*- coding: utf-8 -*-
"""Which circuits to make on a copied floor (no Revit needed).

Revit does not copy circuits: fixtures and panels pasted on another floor
come without them. The copies are found by where they are: an element on
the target floor of the same family type (or, failing that, of the same
family), at the same spot in plan (X, Y) as the source element within a
tolerance, and at the same height above its floor. That is what Paste >
Aligned to Selected Levels gives.

Each circuit with elements on the source floor is planned on the target
floor:

- its panel, when it is on the source floor, is the panel's copy, or else
  the target floor's panel named like it with the floor number swapped
  (DB-F4-01 on L4 -> DB-F3-01 on L3); a circuit whose panel is on another
  floor (a riser board feeding every floor) is fed from that same panel;
- its elements are their copies; elements with no copy (semi-typical
  floors) are left out and listed, and copies already on a circuit of
  that kind are left as they are.
"""
from __future__ import division

import math
import re

# why a circuit is not made (Skipped.reason)
NO_PANEL = "no_panel"           # its panel is on the source floor and has no copy
NONE_FOUND = "none_found"       # none of its elements has a copy
ALREADY = "already"             # every copy is already on a circuit of this kind


# how a source panel's copy was found (PanelMatch.how)
BY_SPOT = "spot"                # same family type at the same spot
BY_NAME = "name"                # named like it, with the floor number swapped
ITSELF = "itself"               # the same panel: the copy puts it where it is (on the axis)
FALLBACK = "fallback"           # none where the copy puts it: the same panel feeds the copy
NOT_FOUND = "not_found"


class Item(object):
    """An element on a floor: its id, family type, family and position."""

    def __init__(self, key, type_key, x, y, z=0.0, family_key=None, flip=False, facing=None):
        self.key = key
        self.type_key = type_key
        self.x = x
        self.y = y
        self.z = z
        self.family_key = family_key
        self.flip = flip                # Revit's Mirrored: the family instance is mirrored
        self.facing = facing            # (x, y) the way it faces in plan, None: not known


def _pairs(source, target, tolerance, dz, z_tolerance, kind):
    cells = {}
    for t in target:
        group = getattr(t, kind)
        if group is None:
            continue
        cell = (group, int(math.floor(t.x / tolerance)), int(math.floor(t.y / tolerance)))
        cells.setdefault(cell, []).append(t)
    pairs = []
    for s in source:
        group = getattr(s, kind)
        if group is None:
            continue
        cx, cy = int(math.floor(s.x / tolerance)), int(math.floor(s.y / tolerance))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in cells.get((group, cx + dx, cy + dy), ()):
                    if z_tolerance is not None and abs(t.z - s.z - dz) > z_tolerance:
                        continue
                    d = math.hypot(t.x - s.x, t.y - s.y)
                    if d <= tolerance:
                        pairs.append((d, s.key, t.key))
    pairs.sort(key=lambda p: p[0])
    return pairs


def match(source, target, tolerance, dz=0.0, z_tolerance=None, by_family=None):
    """{source key: target key}: each source item paired with the nearest
    target item of its type within `tolerance` in plan, one to one; then the
    ones left with the nearest of their family. With z_tolerance, the target
    item must also be dz higher than the source one, within z_tolerance.
    by_family: a set the source keys matched by family only are added to."""
    tolerance = max(tolerance, 1e-9)
    found, taken = {}, set()
    for kind in ("type_key", "family_key"):
        left = [s for s in source if s.key not in found]
        free = [t for t in target if t.key not in taken]
        for _, s, t in _pairs(left, free, tolerance, dz, z_tolerance, kind):
            if s not in found and t not in taken:
                found[s] = t
                taken.add(t)
                if kind == "family_key" and by_family is not None:
                    by_family.add(s)
    return found


class Circuit(object):
    """A circuit of the source model, as far as the plan needs it."""

    def __init__(self, key, kind, elements, panel=None, panel_here=False, slot=0,
                 panel_name="", number=""):
        self.key = key
        self.kind = kind                # system type: power, data, fire alarm...
        self.elements = list(elements)  # keys of its elements on the source floor
        self.panel = panel              # key of its panel, None: no panel
        self.panel_here = panel_here    # its panel is on the source floor
        self.slot = slot                # start slot in the panel, for the order
        self.panel_name = panel_name    # e.g. "DB-1F"
        self.number = number            # circuit number, e.g. "3"

    @property
    def label(self):
        if not self.panel_name:
            return self.number or "(no panel)"
        return "%s / %s" % (self.panel_name, self.number) if self.number else self.panel_name


class Job(object):
    """A circuit to make on the target floor."""

    def __init__(self, circuit, panel, elements, missing, already):
        self.circuit = circuit
        self.panel = panel              # target panel key, None: no panel
        self.elements = elements        # target element keys
        self.missing = missing          # source element keys with no copy
        self.already = already          # target keys already on a circuit of this kind


class Skipped(object):
    def __init__(self, circuit, reason, missing=None):
        self.circuit = circuit
        self.reason = reason
        self.missing = missing or []


def plan(circuits, copies, circuited=(), remote=None):
    """([Job], [Skipped]) for one target floor.

    copies: {source element key: target element key} (panels included).
    circuited: (target key, kind) pairs already on a circuit of that kind.
    remote: for a copy somewhere else (the other tower), {source panel key:
    its copy's key or None} of the panels on other floors; None: those
    panels feed the copies too.
    Jobs come in panel then slot order, so circuit numbers follow the
    source panel's where its slots had no gaps.
    """
    used = set(circuited)
    jobs, skipped = [], []
    for c in sorted(circuits, key=lambda c: (c.panel_name, c.slot, c.key)):
        if c.panel is None:
            panel = None
        elif c.panel_here:
            panel = copies.get(c.panel)
            if panel is None:
                skipped.append(Skipped(c, NO_PANEL))
                continue
        elif remote is None:
            panel = c.panel
        else:
            panel = remote.get(c.panel)
            if panel is None:
                skipped.append(Skipped(c, NO_PANEL))
                continue
        elements, missing, already = [], [], []
        for e in c.elements:
            t = copies.get(e)
            if t is None:
                missing.append(e)
            elif (t, c.kind) in used:
                already.append(t)
            elif t not in elements:
                elements.append(t)
        if not elements:
            skipped.append(Skipped(c, ALREADY if already and not missing else NONE_FOUND,
                                   missing))
            continue
        for t in elements:
            used.add((t, c.kind))
        jobs.append(Job(c, panel, elements, missing, already))
    return jobs, skipped


# ---------------------------------------------------------------- panels by name

def floor_number(level_name):
    """The last number in a level's name (L4, Level 04, 4th Floor -> 4), or None."""
    found = re.findall(r"\d+", level_name or "")
    return int(found[-1]) if found else None


_TOKEN = re.compile(r"^([A-Za-z]*)(\d+)([A-Za-z]*)$")


def floor_name(name, source_level, target_level):
    """The source panel's name with its floor number swapped for the
    target floor's: DB-F4-01 on L4 -> DB-F3-01 on L3, PP-4F-2 -> PP-3F-2.
    The floor number is a part of the name between - _ . or spaces that
    is the source floor's number, with letters stuck to it (F4, L4, 4F)
    or alone (DB-4-01); None when there is no such part, or more than one
    and none of them has letters."""
    a, b = floor_number(source_level), floor_number(target_level)
    if a is None or b is None or a == b or not name:
        return None
    parts = re.split(r"([-_. ]+)", name)
    lettered, bare = [], []
    for i, part in enumerate(parts):
        m = _TOKEN.match(part)
        if m and int(m.group(2)) == a:
            (lettered if m.group(1) or m.group(3) else bare).append(i)
    found = lettered if lettered else bare
    if len(found) != 1:
        return None
    i = found[0]
    m = _TOKEN.match(parts[i])
    digits = m.group(2)
    number = str(b).zfill(len(digits)) if digits.startswith("0") else str(b)
    parts[i] = m.group(1) + number + m.group(3)
    return "".join(parts)


class PanelMatch(object):
    """How a source panel was found on the target floor."""

    def __init__(self, name, how, found=None, looked_for=None, nearest=None, circuits=0,
                 where=None, level=None):
        self.name = name                # source panel name
        self.how = how                  # BY_SPOT, BY_NAME, ITSELF, FALLBACK or NOT_FOUND
        self.where = where              # the copy: "mirrored"..., None: at the same spot
        self.level = level              # a panel on another floor: that floor's name
        self.found = found              # name of the target floor's panel
        self.looked_for = looked_for    # the name looked for, None: no floor number
        self.nearest = nearest          # distance to the nearest panel of its type, None: none
        self.circuits = circuits        # its circuits with elements on the source floor


# ---------------------------------------------------------------- views

class View(object):
    """A plan view: where a source wire is drawn, or a candidate for its copy."""

    def __init__(self, key, name, view_type, level, template=None, family_type=None):
        self.key = key
        self.name = name
        self.view_type = view_type
        self.level = level              # level name
        self.template = template
        self.family_type = family_type


def target_view(source, candidates, level):
    """The view on `level` to draw the copies of wires drawn in `source`:
    a plan of the same kind, best the one named like it (its level name
    swapped for the target's), then the one with the same view template,
    then the same view type. None when the level has no such view."""
    want = source.name.replace(source.level, level) if source.level else None
    best, best_score = None, None
    for v in candidates:
        if v.level != level or v.view_type != source.view_type:
            continue
        score = (4 if want is not None and want != source.name and v.name == want else 0) + \
            (2 if source.template is not None and v.template == source.template else 0) + \
            (1 if v.family_type == source.family_type else 0)
        if best is None or score > best_score or (score == best_score and v.key < best.key):
            best, best_score = v, score
    return best
