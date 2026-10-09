# -*- coding: utf-8 -*-
"""Lays out a Schematic in the office LV schematic style.

* Boards are drawn on their floor: one horizontal band per Revit level,
  with a dashed floor line and label (ROOF FLOOR, GROUND FLOOR...). Main
  boards sit in the SUBSTATION band at the bottom with their transformer.
* A board fed from another board on the same floor is drawn in a second
  tier of that floor's band.
* Feeders between boards are risers: straight up from the outgoing way,
  a horizontal jog just below the fed board, then up into its incomer.
  A riser that meets a board on an intermediate floor jogs around it.

Everything is paper millimetres, +Y up, drawn 1:1.
"""
from __future__ import division

from sld import style, symbols
from sld.geometry import (BOTTOM, CENTER, LEFT, MIDDLE, RIGHT, TOP, Drawing,
                          text_height, text_width, wrap)
from sld.model import (DB_BOX, FEEDER, ISOLATOR, PFC, SPARE, TO_UPS,
                       TRANSFORMER)

SUBSTATION_BAND = -1


class LayoutSettings(object):
    def __init__(self, utility=None, substation_label=None, show_ratings=True):
        self.utility = utility or style.DEFAULT_UTILITY
        self.substation_label = substation_label or style.SUBSTATION_LABEL
        self.show_ratings = show_ratings


class BoardGeom(object):
    """Position and size of one board (x is set during placement)."""

    def __init__(self, board):
        self.board = board
        n = len(board.ways)
        self.name_text, self.info_text = _board_labels(board)
        self.load_rows = _load_rows(board)
        table_w = (symbols.load_table_size(self.load_rows)[0] + style.LOAD_TABLE_MARGIN
                   if self.load_rows else 0.0)
        if board.is_main:
            first = style.BOARD_MARGIN + 10.0
            self.height = style.MAIN_HEIGHT
            self.bus_below_top = style.MAIN_BUS_BELOW_TOP
            span = first + max(n - 1, 0) * style.WAY_PITCH + style.BOARD_MARGIN
            self.info_text = wrap(self.info_text, style.TEXT_MAIN_INFO, 60.0)
            # Incomer (and its lamp group) to the right of the name/info block.
            block = max(text_width(self.name_text, style.TEXT_MAIN_NAME),
                        text_width(self.info_text, style.TEXT_MAIN_INFO)) + 2.0
            self.incomer_offset = max(style.MAIN_INCOMER_FROM_LEFT,
                                      block + symbols.MAIN_LAMPS_LEFT + 3.0)
            # The load table sits top right, clear of the meters and fuse text.
            self.width = max(style.MAIN_MIN_WIDTH, span, self.incomer_offset + 45.0,
                             self.incomer_offset + 32.0 + table_w)
        else:
            first = style.BOARD_MARGIN
            self.height = style.BOARD_HEIGHT
            self.bus_below_top = style.BUS_BELOW_TOP
            span = first + max(n - 1, 0) * style.WAY_PITCH + style.BOARD_MARGIN
            self.info_text = wrap(self.info_text, style.TEXT_BOARD_INFO, 50.0)
            # Taller box when the name + info block would reach the busbar.
            below_bus = (1.0 + style.TEXT_BOARD_NAME * style.LINE_SPACING +
                         text_height(self.info_text, style.TEXT_BOARD_INFO) + 1.5)
            self.height = max(style.BOARD_HEIGHT, below_bus + self.bus_below_top)
            # Incomer to the right of the name/info block in the corner.
            block = max(text_width(self.name_text, style.TEXT_BOARD_NAME),
                        text_width(self.info_text, style.TEXT_BOARD_INFO)) + 1.5
            self.incomer_offset = max(span / 2, block + 2.0)
            # The load table sits bottom right, clear of the incomer label.
            self.width = max(style.BOARD_MIN_WIDTH, span, self.incomer_offset + 12.0,
                             self.incomer_offset + 9.0 + table_w)
        self.way_offsets = [first + i * style.WAY_PITCH for i in range(n)]
        self.left = 0.0
        self.bottom = 0.0
        self.band = 0
        self.tier = 0
        self.remote_ways = set()   # DB ways drawn on a higher floor

    @property
    def key(self):
        return self.board.id

    @property
    def name(self):
        return self.board.name

    @property
    def feed_y(self):
        return self.bottom

    @property
    def row(self):
        return (self.band, self.tier)

    @property
    def right(self):
        return self.left + self.width

    @property
    def top(self):
        return self.bottom + self.height

    @property
    def bus_y(self):
        return self.top - self.bus_below_top

    @property
    def incomer_x(self):
        return self.left + self.incomer_offset

    def way_x(self, way):
        return self.left + self.way_offsets[self.board.ways.index(way)]

    # -- UPS / transformer drawn above the ways that feed it
    def pt_inputs(self, pt):
        return [self.way_x(w) for w in pt.input_ways]

    def ups_span(self, pt):
        xs = self.pt_inputs(pt)
        return min(xs) - style.UPS_MARGIN, max(xs) + style.UPS_MARGIN

    def pt_center(self, pt):
        xs = self.pt_inputs(pt)
        return (min(xs) + max(xs)) / 2

    def pt_bottom(self, pt):
        return self.top + style.UPS_ABOVE_BOARD

    def pt_body_top(self, pt):
        if pt.kind == TRANSFORMER:
            return self.pt_bottom(pt) + 3.4 * style.PT_TRANSFORMER_RADIUS
        return self.pt_bottom(pt) + style.UPS_HEIGHT

    def pt_output_y(self, pt):
        if pt.kind == TRANSFORMER and len(pt.outputs) > 1:
            return self.pt_body_top(pt) + 1.5
        return self.pt_body_top(pt)

    def ups_output_x(self, pt, board):
        n = len(pt.outputs)
        i = pt.outputs.index(board)
        if pt.kind == TRANSFORMER:
            return self.pt_center(pt) + (i - (n - 1) / 2) * 3.0
        left, right = self.ups_span(pt)
        return left + (right - left) * (i + 1) / (n + 1)

    def content_height(self):
        """Height of everything drawn above the box top."""
        h = style.SPARE_HEIGHT + 8.0
        for w in self.board.ways:
            if w.kind == DB_BOX:
                h = max(h, style.TERMINAL_BASE + symbols.db_box_height(w.name, w.loads()))
            elif w.kind == ISOLATOR:
                h = max(h, style.TERMINAL_BASE + style.ISOLATOR_HEIGHT + style.ISOLATOR_HOOK +
                        0.8 + symbols.vertical_length(w.name, style.TEXT_LOAD))
            elif w.kind == SPARE:
                h = max(h, style.SPARE_HEIGHT + 0.8 + symbols.vertical_length("SPARE", style.TEXT_LOAD))
            elif w.kind == TO_UPS:
                h = max(h, style.UPS_ABOVE_BOARD + style.UPS_HEIGHT + 4.0,
                        style.UPS_ABOVE_BOARD + 3.4 * style.PT_TRANSFORMER_RADIUS + 4.0,
                        style.UPS_ABOVE_BOARD + 1.0 + symbols.vertical_length(w.name, style.TEXT_LOAD))
            elif w.kind == PFC:
                h = max(h, style.PFC_ABOVE_BOARD + style.PFC_SIZE + 2.0 +
                        symbols.vertical_length(symbols.pfc_label(), style.TEXT_LOAD))
        return h


class BoxGeom(object):
    """A DB on a higher floor than its board: drawn as a DB box on its own
    floor, fed by a riser (like UDB-FF-01 from USMDB-GF-M)."""

    width = 4.0
    incomer_offset = 2.0

    def __init__(self, way):
        self.way = way
        self.left = 0.0
        self.bottom = 0.0       # board bottom of its row
        self.band = 0
        self.tier = 0

    @property
    def key(self):
        return "box:%s" % self.way.circuit.id

    @property
    def name(self):
        return self.way.name

    @property
    def row(self):
        return (self.band, self.tier)

    @property
    def right(self):
        return self.left + self.width

    @property
    def incomer_x(self):
        return self.left + self.incomer_offset

    @property
    def feed_y(self):
        return self.bottom + style.BOARD_HEIGHT + style.TERMINAL_BASE

    @property
    def top(self):
        return self.feed_y

    def content_height(self):
        return symbols.db_box_height(self.name, self.way.loads())


class Feed(object):
    """Riser from a way (or UPS output) to the incomer of a board."""

    def __init__(self, source, target, way=None, pass_through=None):
        self.source = source      # BoardGeom of the feeding board
        self.target = target      # BoardGeom of the fed board
        self.way = way
        self.pass_through = pass_through
        self.jogs = []            # [row, from x, to x, track]
        self.points = []          # drawn polyline

    def source_x(self):
        if self.way is not None:
            return self.source.way_x(self.way)
        return self.source.ups_output_x(self.pass_through, self.target.board)

    def source_y(self):
        if self.way is not None:
            return self.source.top
        return self.source.pt_output_y(self.pass_through)


class Layout(object):
    def __init__(self, drawing, geoms, bands, feeds):
        self.drawing = drawing
        self.geoms = geoms      # board id -> BoardGeom
        self.bands = bands      # list of (label, floor y)
        self.feeds = feeds


def layout_schematic(schematic, settings=None):
    settings = settings or LayoutSettings()
    geoms = {}
    for b in schematic.boards():
        geoms[b.id] = BoardGeom(b)

    band_names, boxes = _assign_rows(schematic, geoms)
    for box in boxes:
        geoms[box.key] = box
    feeds = _collect_feeds(schematic, geoms, boxes)
    rows = sorted(set(g.row for g in geoms.values()))
    _place_x(schematic, geoms, feeds, rows)
    jog_counts = _route(geoms, feeds, rows)
    floor_ys, row_base = _place_y(geoms, rows, jog_counts)

    d = Drawing()
    for g in geoms.values():
        if isinstance(g, BoardGeom):
            _draw_board(d, g, settings)
    for f in feeds:
        _draw_feed(d, f, row_base)
    for root in schematic.roots:
        _draw_source(d, geoms[root.id], floor_ys[SUBSTATION_BAND], settings)

    x0, _, x1, _ = d.bounds()
    bands = []
    for band, y in sorted(floor_ys.items()):
        label = settings.substation_label if band == SUBSTATION_BAND else band_names[band]
        bands.append((label, y))
        d.dashed_line(x0 - style.FLOOR_MARGIN, x1 + style.FLOOR_MARGIN, y,
                      style.FLOOR_DASH, style.FLOOR_GAP)
        if label:
            d.text(x0 - style.FLOOR_MARGIN, y + 1.5, label, style.TEXT_FLOOR_LABEL,
                   align=LEFT, valign=BOTTOM)
    return Layout(d, geoms, bands, feeds)


# ---------------------------------------------------------------- rows

def _assign_rows(schematic, geoms):
    """Band = floor (by level elevation), tier = stacking within a floor."""
    levels = {}
    for b in schematic.boards():
        if not b.is_main:
            e = b.equipment
            levels.setdefault(e.level_name, e.level_elevation)
        for w in b.ways:
            if w.kind == DB_BOX and w.target is not None:
                levels.setdefault(w.target.level_name, w.target.level_elevation)
    ordered = sorted(levels.items(), key=lambda kv: (kv[1], kv[0]))
    band_of_level = dict((name, i) for i, (name, _) in enumerate(ordered))
    band_names = dict((i, name.upper()) for i, (name, _) in enumerate(ordered))

    def visit(board, parent_geom):
        g = geoms[board.id]
        if board.is_main or parent_geom is None:
            g.band, g.tier = SUBSTATION_BAND, 0
        else:
            band = band_of_level[board.equipment.level_name]
            if band > parent_geom.band:
                g.band, g.tier = band, 0
            else:
                # Same floor as its supply (or lower): stack above it.
                g.band, g.tier = parent_geom.band, parent_geom.tier + 1
        for child in board.children:
            visit(child, g)

    for root in schematic.roots:
        visit(root, None)

    boxes = []
    for b in schematic.boards():
        g = geoms[b.id]
        for w in b.ways:
            if w.kind != DB_BOX or w.target is None:
                continue
            band = band_of_level[w.target.level_name]
            if band > g.band and not (g.band == SUBSTATION_BAND and band == 0):
                box = BoxGeom(w)
                box.band, box.tier = band, 0
                boxes.append(box)
                g.remote_ways.add(w)
    return band_names, boxes


def _collect_feeds(schematic, geoms, boxes):
    feeds = []
    for box in boxes:
        board = next(b for b in schematic.boards() if box.way in b.ways)
        feeds.append(Feed(geoms[board.id], box, way=box.way))
    for b in schematic.boards():
        if b.feed_way is not None:
            feeds.append(Feed(geoms[b.parent.id], geoms[b.id], way=b.feed_way))
        elif b.feed_pass_through is not None:
            feeds.append(Feed(geoms[b.parent.id], geoms[b.id], pass_through=b.feed_pass_through))
    return feeds


# ---------------------------------------------------------------- placement

def _place_x(schematic, geoms, feeds, rows):
    """Left-to-right placement per row, each board as close as possible to
    straight above the way that feeds it."""
    feed_to = dict((f.target.key, f) for f in feeds)
    for row in rows:
        in_row = [g for g in geoms.values() if g.row == row]
        if row[0] == SUBSTATION_BAND:
            order = dict((b.id, i) for i, b in enumerate(schematic.roots))
            in_row.sort(key=lambda g: order.get(g.key, 10 ** 6))
            desired = dict((g.key, None) for g in in_row)
        else:
            desired = {}
            for g in in_row:
                f = feed_to.get(g.key)
                desired[g.key] = f.source_x() - g.incomer_offset if f else None
            in_row.sort(key=lambda g: (desired[g.key] is None,
                                       desired[g.key] or 0.0, g.name))
        cursor = None
        for g in in_row:
            want = desired[g.key]
            if cursor is None:
                g.left = want if want is not None else 0.0
            else:
                g.left = cursor if want is None else max(want, cursor)
            gap = style.BOARD_GAP if isinstance(g, BoardGeom) else 4.0
            cursor = g.right + (gap if row[0] != SUBSTATION_BAND else 45.0)


def _route(geoms, feeds, rows):
    """Plan each riser: where it has to jog sideways.

    A riser goes straight up from its way. In every row it passes through,
    if a board is in the way it jogs (just below that row's boards) to the
    side of the board nearer its destination. In the fed board's row it
    jogs to line up with the incomer. Returns {row: number of jogs}.
    """
    clearance = style.RISER_CLEARANCE
    by_row = {}
    for g in geoms.values():
        by_row.setdefault(g.row, []).append(g)

    def blocker(row, x):
        for g in by_row.get(row, []):
            if g.left - clearance < x < g.right + clearance:
                return g
        return None

    per_row = {}
    for f in feeds:
        x = f.source_x()
        target_x = f.target.incomer_x
        f.jogs = []
        for row in rows:
            if not (f.source.row < row < f.target.row):
                continue
            g = blocker(row, x)
            if g is None:
                continue
            options = [c for c in (g.left - clearance, g.right + clearance)
                       if blocker(row, c) is None] or [g.right + clearance]
            nx = min(options, key=lambda c: abs(c - target_x))
            f.jogs.append([row, x, nx, 0])
            x = nx
        if abs(x - target_x) > 1e-6:
            f.jogs.append([f.target.row, x, target_x, 0])
        for jog in f.jogs:
            per_row.setdefault(jog[0], []).append(jog)
    for row, jogs in per_row.items():
        # Longer jogs lower down, so short ones do not cross them.
        jogs.sort(key=lambda j: (min(j[1], j[2]), -abs(j[2] - j[1])))
        for i, jog in enumerate(jogs):
            jog[3] = i
    return dict((row, len(jogs)) for row, jogs in per_row.items())


def _place_y(geoms, rows, jog_counts):
    """Stack rows bottom-up; returns ({band: floor y}, {row: board bottom})."""
    floor_ys, row_base = {}, {}
    y = 0.0
    for row in rows:
        in_row = [g for g in geoms.values() if g.row == row]
        n = jog_counts.get(row, 0)
        if row[1] == 0:
            floor_ys[row[0]] = y
        if row[0] == SUBSTATION_BAND:
            bottom = y + style.SUBSTATION_STACK
        else:
            bottom = y + style.JOG_BOTTOM_MARGIN + max(n, 1) * style.JOG_TRACK + style.JOG_FIRST
        row_base[row] = bottom
        top = bottom
        for g in in_row:
            g.bottom = bottom
            top = max(top, g.top + g.content_height())
        y = top + style.ROW_TOP_MARGIN
    return floor_ys, row_base


# ---------------------------------------------------------------- drawing

def _board_labels(board):
    """(name, info block) printed in the board's bottom-left corner."""
    e = board.equipment
    if board.is_main:
        info = [e.supply_text(), e.form or style.DEFAULT_MAIN_FORM]
        if e.location:
            info.append("LOCATION: %s" % e.location)
    else:
        info = [e.supply_text(),
                "%s, %s WAYS" % (e.form or style.DEFAULT_FORM, e.ways or len(board.ways))]
        if e.location:
            info.append("LOCATION: %s" % e.location)
        if e.level_name:
            info.append("@ %s" % e.level_name.upper())
    return board.name, "\n".join(info)


def _load_rows(board):
    """Rows of the board's load table, [] when no way has a load."""
    totals = board.load_totals()
    if totals is None:
        return []
    cl, df, dl = totals
    labels = style.LOAD_TABLE_ROWS
    return [(labels[0], "%.2fkW" % cl),
            (labels[1], "%.2f" % df if df is not None else "-"),
            (labels[2], "%.2fkW" % dl)]


def _draw_load_table(d, g):
    if not g.load_rows:
        return
    margin = style.LOAD_TABLE_MARGIN
    if g.board.is_main:
        _, height = symbols.load_table_size(g.load_rows)
        bottom = g.bus_y - 3.0 - height
    else:
        bottom = g.bottom + margin
    symbols.load_table(d, g.right - margin, bottom, g.load_rows)


def _draw_board(d, g, settings):
    b = g.board
    d.rect(g.left, g.bottom, g.right, g.top)
    xs = [g.way_x(w) for w in b.ways]
    bus_l = min(xs + [g.incomer_x]) - 3.0
    bus_r = max(xs + [g.incomer_x]) + 3.0
    d.line(bus_l, g.bus_y, bus_r, g.bus_y)

    for w, x in zip(b.ways, xs):
        y_arc = g.bus_y + (style.BREAKER_ABOVE_BUS if not b.is_main else 4.0)
        d.line(x, g.bus_y, x, y_arc)
        top_arc = symbols.breaker(d, x, y_arc)
        d.line(x, top_arc, x, g.top)
        d.text(x - 0.4, g.bus_y + 0.4, w.label, style.TEXT_WAY, align=RIGHT, valign=BOTTOM)
        lines = w.circuit.breaker_lines() if w.circuit is not None else [style.WAY_DEVICE]
        d.text(x + style.BREAKER_RADIUS + 0.3, y_arc + style.BREAKER_RADIUS, "\n".join(lines),
               style.TEXT_WAY, align=LEFT, valign=MIDDLE)
        _draw_way_end(d, g, w, x, settings)

    for pt in b.pass_throughs:
        _draw_pass_through(d, g, pt)
    _draw_load_table(d, g)

    if b.is_main:
        device = "\n".join(b.equipment.main_incomer_lines())
        symbols.main_incomer(d, g.incomer_x, g.bus_y, g.bottom, g.right, device)
        d.text(g.left + 2.0, g.bottom + 2.0, g.name_text, style.TEXT_MAIN_NAME,
               align=LEFT, valign=BOTTOM)
        d.text(g.left + 2.0, g.bottom + 2.0 + style.TEXT_MAIN_NAME * style.LINE_SPACING,
               g.info_text, style.TEXT_MAIN_INFO, align=LEFT, valign=BOTTOM)
    else:
        xi = g.incomer_x
        y_arc = g.bus_y - style.INCOMER_BREAKER_BELOW_BUS
        d.line(xi, g.bus_y, xi, y_arc + 2 * style.BREAKER_RADIUS)
        symbols.breaker(d, xi, y_arc)
        d.line(xi, y_arc, xi, g.bottom)
        d.text(xi + 2.0, y_arc + style.BREAKER_RADIUS, "\n".join(b.equipment.incomer_lines()),
               style.TEXT_WAY, align=LEFT, valign=MIDDLE)
        d.text(g.left + 1.0, g.bottom + 1.0, g.name_text, style.TEXT_BOARD_NAME,
               align=LEFT, valign=BOTTOM)
        d.text(g.left + 1.5, g.bottom + 1.0 + style.TEXT_BOARD_NAME * style.LINE_SPACING,
               g.info_text, style.TEXT_BOARD_INFO, align=LEFT, valign=BOTTOM)


def _draw_pass_through(d, g, pt):
    y0 = g.pt_bottom(pt)
    if pt.kind != TRANSFORMER:
        left, right = g.ups_span(pt)
        symbols.ups_box(d, left, right, y0, pt.equipment.name)
        return
    xs = g.pt_inputs(pt)
    cx = g.pt_center(pt)
    if len(xs) > 1:
        d.line(min(xs), y0 - 1.5, max(xs), y0 - 1.5)
        d.line(cx, y0 - 1.5, cx, y0)
    top = symbols.small_transformer(d, cx, y0, pt.equipment.name)
    if len(pt.outputs) > 1:
        outs = [g.ups_output_x(pt, b) for b in pt.outputs]
        d.line(cx, top, cx, top + 1.5)
        d.line(min(outs), top + 1.5, max(outs), top + 1.5)


# Room for the rating text above the box top, per way ending.
_RATING_ROOM = {
    DB_BOX: style.TERMINAL_BASE, ISOLATOR: style.TERMINAL_BASE,
    FEEDER: style.TERMINAL_BASE, TO_UPS: style.UPS_ABOVE_BOARD,
    PFC: style.PFC_ABOVE_BOARD,
}


def _draw_way_end(d, g, w, x, settings):
    t = g.top
    if w in g.remote_ways:
        pass  # riser + box drawn by _draw_feed
    elif w.kind == DB_BOX:
        d.line(x, t, x, t + style.TERMINAL_BASE)
        symbols.db_box(d, x, t + style.TERMINAL_BASE, w.name, w.loads())
    elif w.kind == ISOLATOR:
        d.line(x, t, x, t + style.TERMINAL_BASE)
        symbols.isolator(d, x, t + style.TERMINAL_BASE, w.name)
    elif w.kind == SPARE:
        d.line(x, t, x, t + style.SPARE_HEIGHT)
        symbols.spare(d, x, t + style.SPARE_HEIGHT)
    elif w.kind == PFC:
        y0 = t + style.PFC_ABOVE_BOARD
        d.line(x, t, x, y0)
        symbols.pfc(d, x, y0)
    elif w.kind == TO_UPS:
        pt = next(p for p in g.board.pass_throughs if w in p.input_ways)
        joined = pt.kind == TRANSFORMER and len(pt.input_ways) > 1
        d.line(x, t, x, g.pt_bottom(pt) - (1.5 if joined else 0.0))
    # FEEDER: the riser is drawn by _draw_feed.

    if settings.show_ratings:
        lines = w.rating_lines()
        if lines:
            room = _RATING_ROOM.get(w.kind, style.TERMINAL_BASE) - style.RATING_START - 1.5
            text = wrap("\n".join(lines), style.TEXT_RATING, room)
            d.text(x - 0.4, t + style.RATING_START, text, style.TEXT_RATING,
                   align=LEFT, valign=BOTTOM, rotation=symbols.VERTICAL)


def _draw_feed(d, f, row_base):
    xt, yt = f.target.incomer_x, f.target.feed_y
    if isinstance(f.target, BoxGeom):
        symbols.db_box(d, xt, yt, f.target.name, f.target.way.loads())
    points = [(f.source_x(), f.source_y())]
    for row, x0, x1, track in f.jogs:
        y = row_base[row] - style.JOG_FIRST - track * style.JOG_TRACK
        points += [(x0, y), (x1, y)]
    points.append((xt, yt))
    f.points = points
    d.polyline(points)


def _draw_source(d, g, floor_y, settings):
    """Everything under a main board: incoming cable, transformer, supply."""
    b = g.board
    x = g.incomer_x
    y = g.bottom
    cable = b.equipment.incoming_cable
    y_cable = y - 3.5
    d.line(x, y, x, y_cable + 0.6)
    symbols.cable_mark(d, x, y_cable, _cable_label(cable) if cable else None)
    y = y_cable - 0.6
    if b.transformer is not None:
        tr = b.transformer
        y_tr = y - 4.0
        d.line(x, y, x, y_tr)
        y = symbols.transformer(d, x, y_tr, tr.name, tr.description)
        d.line(x, y, x, floor_y + 0.6)
        symbols.cable_mark(d, x, floor_y, "MV CABLE FROM %s" % settings.utility)
        supply = "FROM %s" % settings.utility
    else:
        d.line(x, y, x, floor_y)
        supply = "FROM %s" % settings.utility
    end_y = floor_y - 5.0
    d.line(x, floor_y - 0.6, x, end_y)
    symbols.sealing_end(d, x, end_y)
    d.text(x, end_y - 2.5, supply, style.TEXT_CABLE, align=CENTER, valign=TOP)


def _cable_label(cable):
    """'(7 SC 630mm²\nCu/XLPE/AWA/PVC)': size on the first line, build on the next."""
    if " + " in cable:
        first, rest = cable.split(" + ", 1)
        return "(%s\n+ %s)" % (first, rest)
    tokens = cable.split()
    for i, tok in enumerate(tokens):
        if "/" in tok and i > 0:
            return "(%s\n%s)" % (" ".join(tokens[:i]), " ".join(tokens[i:]))
    return "(%s)" % cable
