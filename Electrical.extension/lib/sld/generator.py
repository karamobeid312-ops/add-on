# -*- coding: utf-8 -*-
"""Standby generator on a life safety board (EMDB), as the office SLD
2506 0EE 320: the board is fed through an ATS, its normal supply from the
MDB way that fed it (left contact), the generator at the bottom.

A generator is added with a button in Power Studio and kept per project
(sld.settings); nothing is read from or written to Revit for it. A spec:

    {"board": "EMDB-G", "name": "G-01", "kva": ""}

kva: blank = sized from the board's connected load: CL (kW) x 1.2 to kVA,
x 1.2 margin, then the next standard generator rating.
"""
from __future__ import division

from sld.model import parse_amps, split_cable, trim_number  # noqa: F401 (used by Power Studio)

KVA_PER_KW = 1.2           # CL in kW -> kVA
SIZING_MARGIN = 1.2        # office margin on top
RATINGS_KVA = (20, 30, 45, 60, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500,
               550, 600, 650, 750, 800, 900, 1000, 1100, 1250, 1500, 1650, 1750, 2000,
               2250, 2500, 3000)
VOLTAGE_TEXT = "0.4kV, 50Hz, 1500 RPM"
EARTH_TEXT = u"2C 150mm² CU CABLE"


def auto_kva(connected_kw):
    """Next standard rating above CL x 1.2 x 1.2; None when CL is unknown."""
    if not connected_kw:
        return None
    need = connected_kw * KVA_PER_KW * SIZING_MARGIN
    for k in RATINGS_KVA:
        if k >= need - 1e-6:
            return k
    step = 250
    return int(-(-need // step) * step)


class AtsInfo(object):
    """The transfer switch drawn under the board (name and info lines)."""

    def __init__(self, name, rating, location):
        self.name = name
        self.rating = rating
        self.location = location

    def info(self):
        lines = []
        if self.rating:
            lines.append("%sA,4P" % trim_number(self.rating, 1))
        if self.location:
            lines.append("LOCATION: %s" % self.location)
        return lines


class Generator(object):
    def __init__(self, name, kva, board):
        self.name = name
        self.kva = kva
        self.board = board              # the life safety board it backs up
        self.ats = None                 # AtsInfo
        self.cable = ""                 # ATS -> board (normal + standby share it)
        self.gen_cable = ""             # generator -> ATS
        self.normal_board = None        # board whose way is the normal supply
        self.normal_way = None
        self.normal_text = ""           # 'FROM ...' when there is no such way

    def lines(self):
        """Text under the generator, as the office SLD."""
        out = ["%s PRIME GENERATOR" % self.name, VOLTAGE_TEXT]
        if self.kva:
            out.append("%s kVA" % trim_number(self.kva, 0))
        return out


def apply_generators(schematic, specs, utility="TAQA"):
    """Put a generator and ATS under each spec's board. The board is drawn
    beside the board that feeds it (substation band), its feed way kept as
    the ATS's normal supply. Returns warnings."""
    from sld.riser import _detach
    warnings = []
    by_name = dict((b.name.strip().upper(), b) for b in schematic.boards())
    on_riser = set(t.board.id for r in getattr(schematic, "risers", []) for t in r.taps)
    specs = list(specs or [])
    typed = set((s.get("board") or "").strip().upper() for s in specs)
    for b in schematic.boards():
        g = b.model_generator
        if g is not None and b.name.strip().upper() not in typed:
            specs.append({"board": b.name, "name": g.name, "model": True})
    count = 0
    for spec in specs:
        typed = (spec.get("board") or "").strip()
        b = by_name.get(typed.upper())
        if b is None:
            warnings.append("Generator: %s is not in the model." % typed)
            continue
        if b.id in on_riser or getattr(b, "generator", None) is not None:
            warnings.append("Generator: %s cannot take a generator here." % b.name)
            continue
        count += 1
        name = (spec.get("name") or "").strip() or "G-%02d" % count
        kva = parse_amps(spec.get("kva")) or auto_kva((b.load_totals() or (None,))[0])
        gen = Generator(name, kva, b)

        e = b.equipment
        model_ats = b.ats
        parent, way = (b.parent, b.feed_way)
        if b.feed_pass_through is not None:
            parent, way = b.feed_pass_through.board, None
        if parent is not None:
            _detach(schematic, b)
            if way is not None:
                gen.normal_board, gen.normal_way = parent, way
            else:
                gen.normal_text = "FROM %s" % parent.name
        else:
            gen.normal_text = "FROM %s" % ((e.fed_by or "").strip().upper() or utility)

        cable = ""
        if way is not None and way.circuit is not None:
            cable = way.circuit.cable_text()
        gen.cable = cable or e.incoming_cable or e.feeder_cable
        gen.gen_cable = split_cable(gen.cable)[0] if gen.cable else ""
        rating = parse_amps(spec.get("ats_rating")) or e._incomer()[0]
        if model_ats is not None:
            gen.ats = AtsInfo(model_ats.name, rating, model_ats.location or e.location)
        else:
            gen.ats = AtsInfo("ATS", rating, spec.get("ats_location") or e.location)
        b.ats = None
        b.transformer = None
        b.generator = gen

        # beside the board feeding it, in the substation band
        if b in schematic.roots:
            schematic.roots.remove(b)
        after = _root_of(gen.normal_board) if gen.normal_board is not None else None
        if after is not None and after in schematic.roots:
            schematic.roots.insert(schematic.roots.index(after) + 1, b)
        else:
            schematic.roots.append(b)
    return warnings


def _root_of(board):
    while board is not None and board.parent is not None:
        board = board.parent
    return board


# ---------------------------------------------------------------- Power Studio

def board_generator(specs, board_name):
    """The spec of a board's generator, or None."""
    key = (board_name or "").strip().upper()
    return next((s for s in specs or []
                 if (s.get("board") or "").strip().upper() == key), None)


def set_generator(specs, board_name, on):
    """Specs with the board's generator added (named G-01, G-02...) or
    removed."""
    key = (board_name or "").strip().upper()
    out = [dict(s) for s in specs or [] if (s.get("board") or "").strip().upper() != key]
    if on:
        used = set((s.get("name") or "").upper() for s in out)
        n = 1
        while "G-%02d" % n in used:
            n += 1
        out.append({"board": board_name, "name": "G-%02d" % n, "kva": ""})
    return out


def clean_specs(specs):
    out = []
    for s in specs or []:
        board = (s.get("board") or "").strip()
        if board:
            out.append({"board": board, "name": (s.get("name") or "").strip(),
                        "kva": (u"%s" % (s.get("kva") or "")).strip()})
    return out
