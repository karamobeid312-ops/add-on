# -*- coding: utf-8 -*-
"""Voltage drop calculation, as the office 'VOLTAGE DROP CALCULATION SHEET'.

For every cable (FROM board -> TO board or load):

    kVA          = load kW / PF
    I (A)        = kVA x 1000 / (sqrt(3) x 400 V)      single phase: / 230 V
    breaker      In >= 1.1 x I
    cable        Iz = rating x runs x Cb x Ca x Cr x Cg >= In
    V.D (V)      = mV/A/m / runs x L (m) x I (A) / 1000
    V.D (%)      = V.D / V x 100
    cumulative   = V.D (%) + cumulative V.D (%) of the cable feeding FROM

Limits: 2.5 % from the transformer to the main board, 4 % in total to the
final load. The total starts again after a transformer or a UPS. Single
phase cables use the two core drop, 2/sqrt(3) x the three phase mV/A/m.

Kept free of Revit imports so it runs under IronPython 2.7, CPython 3 and
pytest.
"""
from __future__ import division

import math
import re

from vdrop import tables
from vdrop.parse import Cable, format_number

SQRT3 = math.sqrt(3)
EPS = 1e-9
LOW_VOLTAGE = (100, 1100)   # V, a voltage outside it is reported

# what feeds a cable
BOARD = "board"
TRANSFORMER = "transformer"
UPS = "ups"

MDL = "MDL"   # maximum demand load
TCL = "TCL"   # total connected load


class Settings(object):
    """Project-wide values of the calculation (header of the office sheet)."""

    def __init__(self, voltage_3ph=400.0, voltage_1ph=230.0, power_factor=0.85,
                 limit_total=4.0, limit_transformer=2.5,
                 insulation=tables.DEFAULT_INSULATION, installation=tables.TRAY,
                 air_temperature=35, ground_temperature=35, depth=0,
                 soil_resistivity=0, grouping=0.85):
        self.voltage_3ph = voltage_3ph
        self.voltage_1ph = voltage_1ph
        self.power_factor = power_factor
        self.limit_total = limit_total
        self.limit_transformer = limit_transformer
        self.insulation = insulation
        self.installation = installation
        self.air_temperature = air_temperature
        self.ground_temperature = ground_temperature
        self.depth = depth
        self.soil_resistivity = soil_resistivity
        self.grouping = grouping


class Feeder(object):
    """One cable read from the model: a row of the voltage drop sheet.

    source_id/target_id link the rows: the row whose target_id is this
    row's source_id feeds it. mdl_kw set (demand or typed load) means the
    current is worked out from it, otherwise from tcl_kw.
    """

    def __init__(self, id, source_id, source, target, target_id=None, length=None,
                 phases=3, voltage=None, tcl_kw=None, mdl_kw=None, power_factor=None,
                 breaker=None, installation=None, cable=None, source_kind=BOARD,
                 order=None, ref=None, notes=None):
        self.id = id
        self.source_id = source_id
        self.source = source or ""
        self.target = target or ""
        self.target_id = target_id
        self.length = length
        self.phases = phases
        self.voltage = voltage
        self.tcl_kw = tcl_kw
        self.mdl_kw = mdl_kw
        self.power_factor = power_factor
        self.breaker = breaker
        self.installation = installation
        self.cable = cable
        self.source_kind = source_kind
        self.order = order        # sort key among the cables of a board
        self.ref = ref            # Revit element id, for links
        self.notes = list(notes or [])


class Row(object):
    """Calculated values of one cable, named after the office sheet columns."""

    def __init__(self, feeder):
        self.feeder = feeder
        self.number = ""
        self.parent = None
        self.children = []
        self.problems = list(feeder.notes)
        self.suggestions = []
        for name in ("phases", "voltage", "power_factor", "load_kw", "basis", "kva",
                     "current", "installation", "insulation", "runs", "cores", "size",
                     "rating", "total_rating", "depth", "cb", "temperature", "ca",
                     "resistivity", "cr", "cg", "capacity", "mv_table", "mv", "mv_row",
                     "vd_volts", "vd_percent", "upstream", "total_percent", "limit",
                     "breaker_ok", "cable_ok", "vd_ok"):
            setattr(self, name, None)
        self.resets = False

    @property
    def single_core(self):
        return self.cores == 1

    @property
    def failed(self):
        return False in (self.breaker_ok, self.cable_ok, self.vd_ok)

    @property
    def checks(self):
        """Names of the failed checks."""
        out = []
        if self.breaker_ok is False:
            out.append("breaker < 1.1 x Ib")
        if self.cable_ok is False:
            out.append("cable Iz < In")
        if self.vd_ok is False:
            out.append("V.D %s%% > %s%%" % (format_number(self.total_percent),
                                            format_number(self.limit)))
        return out

    def status(self):
        """'OK', 'FAIL', or 'INCOMPLETE' when a value is missing."""
        if self.failed:
            return "FAIL"
        if self.total_percent is None or self.problems:
            return "INCOMPLETE"
        return "OK"

    def remarks(self):
        return "; ".join(self.checks + self.problems + self.suggestions)

    def cable_text(self):
        return cable_text(self.runs, self.cores, self.size)


class Section(object):
    """Cables fed from one source: a transformer, or a main board."""

    def __init__(self, title, rows):
        self.title = title
        self.rows = rows      # in sheet order, parents before children


class Result(object):
    def __init__(self, sections, warnings):
        self.sections = sections
        self.warnings = warnings

    def rows(self):
        for section in self.sections:
            for row in section.rows:
                yield row


def cable_text(runs, cores, size):
    """'4Cx16mm²', '4x(1Cx630mm²)'."""
    if not size:
        return ""
    text = u"%sCx%smm²" % (cores or "", format_number(size))
    if runs and runs > 1:
        text = u"%dx(%s)" % (runs, text)
    return text


def natural_key(text):
    return [(0, int(tok), "") if tok.isdigit() else (1, 0, tok.lower())
            for tok in re.findall(r"\d+|\D+", text or "")]


def _sort_key(row):
    order = row.feeder.order
    return ((0, order) if order is not None else (1, ()), natural_key(row.feeder.target))


# ---------------------------------------------------------------- one cable

def _cable_values(row, size, runs=None):
    """(rating of one cable, Cb, Cr, Iz, mV/A/m of one cable) for `row`'s
    cable in another size or number of runs."""
    runs = runs or row.runs
    single = row.single_core
    rating = tables.ampacity(row.insulation, single, size, row.installation)
    cb = tables.depth_factor(row.depth, single, row.installation, size)
    cr = tables.resistivity_factor(row.resistivity, single, row.installation, size)
    capacity = None
    if None not in (rating, cb, row.ca, cr, row.cg):
        capacity = rating * runs * cb * row.ca * cr * row.cg
    mv = tables.mv_per_a_m(single, size)
    if mv is not None and row.phases == 1:
        mv *= 2 / SQRT3
    return rating, cb, cr, capacity, mv


def _noted(row, *starts):
    """True when a problem about this was already noted (e.g. while reading)."""
    return any(p.startswith(starts) for p in row.problems)


def calculate_row(row, settings):
    """Everything but the cumulative voltage drop."""
    f = row.feeder
    row.phases = 1 if f.phases == 1 else 3
    row.voltage = f.voltage or (settings.voltage_1ph if row.phases == 1 else settings.voltage_3ph)
    if not LOW_VOLTAGE[0] <= row.voltage <= LOW_VOLTAGE[1]:
        row.problems.append("voltage %s V looks wrong" % format_number(row.voltage))
    pf = f.power_factor
    row.power_factor = pf if pf is not None and 0 < pf <= 1 else settings.power_factor
    row.basis = MDL if f.mdl_kw is not None else TCL
    row.load_kw = f.mdl_kw if f.mdl_kw is not None else f.tcl_kw
    if row.load_kw is None:
        row.problems.append("no load in the model")
    else:
        row.kva = row.load_kw / row.power_factor
        root = SQRT3 if row.phases == 3 else 1.0
        row.current = row.kva * 1000.0 / (root * row.voltage)

    cable = f.cable or Cable()
    row.runs = cable.runs or 1
    row.cores = cable.cores or (4 if row.phases == 3 else 2)
    row.size = cable.size
    row.insulation = cable.insulation or settings.insulation
    row.installation = f.installation or settings.installation
    in_air = row.installation == tables.TRAY
    row.depth = 0 if in_air else settings.depth
    row.temperature = settings.air_temperature if in_air else settings.ground_temperature
    row.resistivity = 0 if in_air else settings.soil_resistivity
    row.ca = tables.temperature_factor(row.temperature, row.installation)
    row.cg = settings.grouping

    if row.size is None:
        if not _noted(row, "VD Cable", "wire size", "no wire size"):
            row.problems.append("no cable size")
    else:
        row.rating, row.cb, row.cr, row.capacity, row.mv = _cable_values(row, row.size)
        row.mv_table = tables.mv_per_a_m(row.single_core, row.size)
        name = u"%s %s" % (row.cable_text(), row.insulation)
        if row.rating is None:
            row.problems.append(u"no rating for %s in %s" % (name, row.installation))
        else:
            row.total_rating = row.rating * row.runs
        if row.mv is None:
            row.problems.append(u"no mV/A/m for %s" % name)
        else:
            row.mv_row = row.mv / row.runs

    if f.length is None and not _noted(row, "VD Length"):
        row.problems.append("no VD Length")
    if None not in (f.length, row.mv_row, row.current):
        row.vd_volts = row.mv_row * f.length * row.current / 1000.0
        row.vd_percent = row.vd_volts / row.voltage * 100.0

    if f.breaker is not None and row.current is not None:
        row.breaker_ok = f.breaker >= 1.1 * row.current - EPS
    needed = f.breaker if f.breaker is not None else row.current
    if row.capacity is not None and needed is not None:
        row.cable_ok = row.capacity >= needed - EPS
    row.limit = (settings.limit_transformer if f.source_kind == TRANSFORMER
                 else settings.limit_total)


def total_row(row):
    """Cumulative voltage drop, once the parent row has its total."""
    parent = row.parent
    row.resets = parent is None or row.feeder.source_kind in (TRANSFORMER, UPS)
    if row.resets:
        row.upstream = 0.0
    elif parent.total_percent is None:
        if row.vd_percent is not None:
            row.problems.append("no total: %s -> %s is incomplete" % (
                parent.feeder.source, parent.feeder.target))
    else:
        row.upstream = parent.total_percent
    if row.vd_percent is not None and row.upstream is not None:
        row.total_percent = row.vd_percent + row.upstream
        row.vd_ok = row.total_percent <= row.limit + EPS


MAX_EXTRA_RUNS = 12


def suggest(row):
    """Breaker, cable size or runs that would pass, for a failed row."""
    needed = row.feeder.breaker
    if row.breaker_ok is False:
        needed = tables.next_breaker(1.1 * row.current)
        row.suggestions.append("use breaker %sA" % needed if needed else "check breaker")
    needed = needed or row.current
    too_small = row.cable_ok is False or (
        row.capacity is not None and needed is not None and row.capacity < needed - EPS)
    fix_vd = row.vd_ok is False
    if fix_vd and row.upstream >= row.limit - EPS:
        row.suggestions.append("already over the limit upstream")
        fix_vd = False
    if not (too_small or fix_vd) or row.size is None or row.current is None:
        return
    for runs in range(row.runs, row.runs + MAX_EXTRA_RUNS + 1):
        for size in tables.SIZES:
            if runs == row.runs and size <= row.size:
                continue
            _, _, _, capacity, mv = _cable_values(row, size, runs)
            if capacity is None or mv is None or capacity < needed - EPS:
                continue
            if fix_vd:
                vd = mv / runs * row.feeder.length * row.current / 1000.0
                if vd / row.voltage * 100.0 + row.upstream > row.limit + EPS:
                    continue
            row.suggestions.append(u"use %s" % cable_text(runs, row.cores, size))
            return
    row.suggestions.append("check cable")


# ---------------------------------------------------------------- all cables

def _link(rows):
    """Parent/children from source/target ids. Returns warnings."""
    warnings = []
    by_target = {}
    for row in rows:
        t = row.feeder.target_id
        if t is None:
            continue
        if t in by_target:
            warnings.append("%s is fed by more than one cable; using %s -> %s." % (
                row.feeder.target, by_target[t].feeder.source, by_target[t].feeder.target))
            continue
        by_target[t] = row
    for row in rows:
        parent = by_target.get(row.feeder.source_id)
        if parent is not None and parent is not row:
            row.parent = parent
            parent.children.append(row)
    for row in rows:
        row.children.sort(key=_sort_key)
    return warnings


def _walk(row, out):
    out.append(row)
    for child in row.children:
        _walk(child, out)


def _sections(rows, warnings):
    roots = [r for r in rows if r.parent is None]
    reached = set()
    stack = list(roots)
    while stack:
        r = stack.pop()
        reached.add(id(r))
        stack.extend(r.children)
    # Feed loops: cut them at the first cable found.
    for row in sorted(rows, key=_sort_key):
        if id(row) in reached:
            continue
        warnings.append("%s -> %s is part of a feed loop." % (row.feeder.source, row.feeder.target))
        row.parent.children.remove(row)
        row.parent = None
        roots.append(row)
        stack = [row]
        while stack:
            r = stack.pop()
            reached.add(id(r))
            stack.extend(r.children)

    groups, order = {}, []
    for root in sorted(roots, key=_sort_key):
        key = root.feeder.source_id
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(root)
    sections = []
    for key in order:
        group = groups[key]
        first = group[0].feeder
        incomer = len(group) == 1 and first.source_kind == TRANSFORMER
        sections.append((first.target if incomer else first.source, group, incomer))
    sections.sort(key=lambda s: natural_key(s[0]))
    return sections


def _number(row, number):
    row.number = number
    for i, child in enumerate(row.children):
        _number(child, "%s.%d" % (number, i + 1))


def calculate(feeders, settings=None):
    """Rows of every cable, grouped in sections as the office sheet."""
    settings = settings or Settings()
    rows = [Row(f) for f in feeders]
    warnings = _link(rows)
    for row in rows:
        calculate_row(row, settings)

    sections = []
    for k, (title, roots, incomer) in enumerate(_sections(rows, warnings)):
        ordered = []
        for i, root in enumerate(roots):
            _number(root, str(k + 1) if incomer else "%d.%d" % (k + 1, i + 1))
            _walk(root, ordered)
        for row in ordered:        # parents come first
            total_row(row)
            if row.failed:
                suggest(row)
        sections.append(Section(title, ordered))
    return Result(sections, warnings)
