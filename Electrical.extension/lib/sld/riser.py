# -*- coding: utf-8 -*-
"""Busbar risers: high-rise boards fed by tap-offs on a bus bar riser
instead of each by its own cable (office SLD 2506 0EE 320).

A riser is fed from one way of a board (normally the MDB). The boards on
it are taken off their feeders and drawn on the riser instead, each on
its own floor. A board marked "typical of" another is drawn
as a box "SMDB-T-6 / DB SAME AS SMDB-T-1"; the others are drawn in full.

Risers are typed in Power Studio and kept per project (sld.settings); no
Revit parameter is read or written for them. A riser is a dict:

    {"name": "RISER-1", "rating": "1000", "material": "COPPER",
     "fault": "50", "source": "MDB-01", "way": "",
     "taps": [{"board": "SMDB-T-1", "rating": "160", "typical": ""}, ...]}

way: the label of the source board's way feeding the riser ('' = the
first way that fed one of its boards, else a new way drawn only).
"""
from __future__ import division

from sld import style
from sld.model import (CircuitInfo, Way, _next_way_number, frame_rating,
                       natural_key, parse_amps, trim_number)

RISER = "riser"            # way kind: a way feeding a bus bar riser
RISER_ID = "riser:"
MATERIALS = ("COPPER", "ALUMINIUM")


class Tap(object):
    """One tap-off unit on a riser and the board it feeds."""

    def __init__(self, board, rating, typical_of=""):
        self.board = board
        self.rating = rating            # tap-off trip (A), None when unknown
        self.typical_of = typical_of    # name of the board it is the same as
        self.cable = ""                 # cable from the tap-off to the board
        self.length_m = None
        self.vd_percent = None

    @property
    def is_typical(self):
        return bool(self.typical_of)

    def rating_text(self):
        return "%sA" % trim_number(self.rating, 1) if self.rating else ""

    def cable_lines(self):
        from sld.model import split_cable
        lines = split_cable(self.cable)
        vd = []
        if self.length_m is not None:
            vd.append("L:%sm" % trim_number(self.length_m, 1))
        if self.vd_percent is not None:
            vd.append("V.D:%.2f%%" % self.vd_percent)
        if vd:
            lines.append("  ".join(vd))
        return lines


class Riser(object):
    def __init__(self, name, rating=None, material="COPPER", fault=""):
        self.name = name
        self.rating = rating            # A
        self.material = material or "COPPER"
        self.fault = fault or ""        # kA, as typed
        self.source = None              # Board feeding it
        self.way = None                 # Way on the source board
        self.taps = []                  # bottom (lowest floor) first

    def connected_kw(self):
        total, known = 0.0, False
        for t in self.taps:
            totals = t.board.load_totals()
            if totals is not None:
                total += totals[0]
                known = True
        return total if known else None

    def loads(self):
        cl, dl, known = 0.0, 0.0, False
        for t in self.taps:
            totals = t.board.load_totals()
            if totals is None:
                continue
            known = True
            cl += totals[0]
            dl += totals[2] if totals[2] is not None else totals[0]
        return (cl, dl) if known else (None, None)

    def label(self):
        """'1000A TPN+E COPPER BUS BAR RISER-1   450.60KW   50KA'"""
        parts = []
        head = "%sA " % trim_number(self.rating, 1) if self.rating else ""
        parts.append("%sTPN+E %s BUS BAR %s" % (head, self.material.upper(), self.name.upper()))
        kw = self.connected_kw()
        if kw is not None:
            parts.append("%.2fKW" % kw)
        fault = parse_amps(self.fault)
        if fault is not None:
            parts.append("%sKA" % trim_number(fault, 1))
        return "   ".join(parts)


def _floor_key(board):
    e = board.equipment
    return (e.level_elevation, natural_key(board.name))


def _detach(schematic, board):
    """Take a board out of the tree; returns the way that fed it, if any."""
    way = board.feed_way
    parent = board.parent
    if parent is not None:
        if board in parent.children:
            parent.children.remove(board)
    if board.feed_pass_through is not None and board in board.feed_pass_through.outputs:
        board.feed_pass_through.outputs.remove(board)
    if board in schematic.roots:
        schematic.roots.remove(board)
    board.parent, board.feed_way, board.feed_pass_through = None, None, None
    return parent, way


def _breaker(rating):
    """(device, frame) of the breaker on a new riser way."""
    if rating is None:
        return style.WAY_DEVICE, ""
    if rating >= style.ACB_FROM:
        return style.MAIN_INCOMER_DEVICE, trim_number(frame_rating(rating, style.ACB_FRAMES), 1)
    return style.WAY_DEVICE, trim_number(frame_rating(rating), 1)


def apply_risers(schematic, specs, numbering="slots"):
    """Put the boards of each riser spec on its riser. Adds
    schematic.risers and returns warnings."""
    warnings = []
    risers = []
    by_name = dict((b.name.strip().upper(), b) for b in schematic.boards())
    taken = set()
    for spec in specs or []:
        name = (spec.get("name") or "").strip() or "RISER-%d" % (len(risers) + 1)
        boards = []
        for t in spec.get("taps") or []:
            b = by_name.get((t.get("board") or "").strip().upper())
            if b is None:
                warnings.append("%s: %s is not in the model." % (name, t.get("board")))
                continue
            if b.is_main or b.id in taken:
                warnings.append("%s: %s cannot be on this riser." % (name, b.name))
                continue
            boards.append((b, t))
            taken.add(b.id)
        if not boards:
            continue
        typed = (spec.get("source") or "").strip()
        source = by_name.get(typed.upper()) if typed else _auto_source(schematic, by_name, boards)
        if source is None:
            warnings.append("%s: the board feeding it (%s) is not in the model; not drawn." % (
                name, typed or "none found"))
            continue
        boards = [(b, t) for b, t in boards if b is not source]

        riser = Riser(name, parse_amps(spec.get("rating")), spec.get("material") or "COPPER",
                      spec.get("fault") or source.equipment.fault_level or "")
        riser.source = source
        old_ways = []
        for b, t in boards:
            parent, way = _detach(schematic, b)
            if way is not None and parent is not None:
                old_ways.append((parent, way, b))
            tap = Tap(b, parse_amps(t.get("rating")) or b.equipment._incomer()[0],
                      (t.get("typical") or "").strip())
            # the tap-off cable: the way that fed it, else Feeder_* on the board
            e, c = b.equipment, (way.circuit if way is not None else None)
            tap.cable = (c.cable_text() if c is not None else "") or e.feeder_cable
            tap.length_m = c.length_m if c is not None and c.length_m is not None \
                else e.feeder_length
            tap.vd_percent = c.vd_percent if c is not None and c.vd_percent is not None \
                else e.feeder_vd
            riser.taps.append(tap)
        riser.taps.sort(key=lambda t: _floor_key(t.board))
        if riser.rating is None:
            riser.rating = auto_rating([t.rating for t in riser.taps])
        names = set(t.board.name.upper() for t in riser.taps)
        for t in riser.taps:
            if t.typical_of and (t.typical_of.upper() not in names or
                                 t.typical_of.upper() == t.board.name.upper()):
                warnings.append("%s: %s is typical of %s, which is not on the riser; drawn "
                                "in full." % (name, t.board.name, t.typical_of))
                t.typical_of = ""
            elif t.typical_of:
                master = next(x for x in riser.taps if x.board.name.upper() == t.typical_of.upper())
                if master.typical_of:
                    t.typical_of = master.typical_of     # same as the same board

        # the way feeding the riser
        wanted = (spec.get("way") or "").strip()
        way = None
        if wanted:
            way = next((w for w in source.ways if (w.label or "") == wanted), None)
            if way is None:
                warnings.append("%s: way %s is not on %s; drawn on a new way." % (
                    name, wanted, source.name))
        if way is None:
            own = [w for p, w, _ in old_ways if p is source]
            if own:
                way = min(own, key=source.ways.index)
        for p, w, b in old_ways:
            if w is not way and w in p.ways:
                p.ways.remove(w)
        if way is None:
            device, frame = _breaker(riser.rating)
            c = CircuitInfo(RISER_ID + name, source.id, poles="4",
                            rating="%sA" % trim_number(riser.rating, 1) if riser.rating else "",
                            device=device, frame=frame)
            label = str(_next_way_number([w.label for w in source.ways])) \
                if numbering != "revit" else ""
            way = Way(c, RISER, label, name)
            source.ways.append(way)
        else:
            way.target = None
            way.kind = RISER
            way.name = name
            if riser.rating and way.circuit is not None:
                # the breaker feeding the bar takes the riser's rating
                device, frame = _breaker(riser.rating)
                way.circuit.rating = "%sA" % trim_number(riser.rating, 1)
                way.circuit.device, way.circuit.frame = device, frame
        way.riser = riser
        riser.way = way
        risers.append(riser)
    schematic.risers = risers
    return warnings


# ---------------------------------------------------------------- typicals

def board_signature(board):
    """What makes two boards the same on the SLD: their ways (breaker and
    what each feeds, by kind) and their incomer."""
    ways = tuple((w.kind, tuple(w.breaker_lines()), w.circuit.cable_text() if w.circuit else "")
                 for w in board.ways)
    return (tuple(board.equipment.incomer_lines()), ways)


def suggest_typicals(boards):
    """{board name: master name} for boards whose ways are the same as a
    board on a lower floor (the lowest one is drawn in full)."""
    groups = {}
    for b in sorted(boards, key=_floor_key):
        if not b.ways:
            continue
        groups.setdefault(board_signature(b), []).append(b)
    out = {}
    for group in groups.values():
        for b in group[1:]:
            out[b.name] = group[0].name
    return out


def tap_rating(board):
    """Default tap-off rating: the board's incoming breaker trip."""
    return board.equipment._incomer()[0]


def clean_specs(specs):
    """Specs as kept in the settings (plain text values)."""
    out = []
    for s in specs or []:
        taps = [dict(board=u"%s" % (t.get("board") or ""), rating=u"%s" % (t.get("rating") or ""),
                     typical=u"%s" % (t.get("typical") or "")) for t in s.get("taps") or []
                if t.get("board")]
        out.append(dict(name=u"%s" % (s.get("name") or ""), rating=u"%s" % (s.get("rating") or ""),
                        material=u"%s" % (s.get("material") or "COPPER"),
                        fault=u"%s" % (s.get("fault") or ""), source=u"%s" % (s.get("source") or ""),
                        way=u"%s" % (s.get("way") or ""), taps=taps))
    return out



# ---------------------------------------------------------------- automatic values

RATINGS = (400, 630, 800, 1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000)


def auto_rating(tap_ratings):
    """Riser rating: the smallest standard bus bar that takes the sum of its
    tap-offs (5 x 160A -> 800A, 6 x 160A -> 1000A); None when unknown."""
    known = [r for r in tap_ratings if r]
    if not known:
        return None
    total = sum(known)
    return float(next((r for r in RATINGS if r >= total - 1e-6), RATINGS[-1]))


def _auto_source(schematic, by_name, boards):
    """The board feeding a riser when none is typed: the board that fed its
    first board (a circuit or Fed_By), else the first main board."""
    for b, _ in boards:
        if b.parent is not None:
            return b.parent
        fed_by = by_name.get((b.equipment.fed_by or "").strip().upper())
        if fed_by is not None:
            return fed_by
    return next((r for r in schematic.roots if r.is_main), None)


# ---------------------------------------------------------------- Power Studio
# Each board's "Bus bar riser" tick, riser name and "Typical of" (board
# fields) are kept as the riser specs above.

DEFAULT_RISER = "RISER-1"


def board_mark(specs, board_name):
    """(on a riser, riser name, typical of) of a board."""
    key = (board_name or "").upper()
    for s in specs or []:
        for t in s.get("taps") or []:
            if (t.get("board") or "").upper() == key:
                return True, s.get("name") or DEFAULT_RISER, t.get("typical") or ""
    return False, "", ""


def set_mark(specs, board_name, on, riser_name="", typical=""):
    """Specs with the board on riser `riser_name` (or on none); risers
    left with no boards are dropped."""
    key = (board_name or "").upper()
    out = []
    for s in specs or []:
        s = dict(s)
        s["taps"] = [t for t in s.get("taps") or [] if (t.get("board") or "").upper() != key]
        out.append(s)
    if on:
        name = (riser_name or DEFAULT_RISER).strip().upper()
        spec = next((s for s in out if (s.get("name") or "").upper() == name), None)
        if spec is None:
            spec = dict(name=name, rating="", material="COPPER", fault="", source="", way="",
                        taps=[])
            out.append(spec)
        spec["taps"].append(dict(board=board_name, rating="", typical=(typical or "").strip()))
    return [s for s in out if s["taps"]]


def riser_names(specs):
    names = [s.get("name") for s in specs or [] if s.get("name")]
    n = 1
    while "RISER-%d" % n in names:
        n += 1
    return names + ["RISER-%d" % n]
