# -*- coding: utf-8 -*-
"""Lays out a Schematic in the office LV schematic style.

* Boards are drawn on their floor: one horizontal band per Revit level,
  with a dashed floor line and label (ROOF FLOOR, GROUND FLOOR...). Main
  boards sit in the SUBSTATION band at the bottom with their transformer
  and the utility supply. A board or DB fed from nothing in the model is
  drawn on its own floor, with no supply under it.
* A board fed from another board on the same floor is drawn in a second
  tier of that floor's band.
* Feeders between boards are risers: straight up from the outgoing way,
  a horizontal jog just below the fed board, then up into its incomer.
  A riser that meets a board on an intermediate floor jogs around it.
* A bus bar riser (sld.riser) is drawn compact above the way feeding it,
  as the office SLD: a tall bar with its tap-offs in floor order, typical
  boards as 'DB SAME AS' boxes and the other boards in full beside it.

Everything is paper millimetres, +Y up, drawn 1:1.
"""
from __future__ import division

from sld import style, symbols
from sld.geometry import (BOTTOM, CENTER, LEFT, MIDDLE, RIGHT, TOP, Drawing,
                          text_height, text_width, wrap)
from sld.model import (ATS, DB_BOX, FEEDER, ISOLATOR, PFC, SPARE, TO_UPS, split_cable,
                       TRANSFORMER, trim_number)

SUBSTATION_BAND = -1


class LayoutSettings(object):
    def __init__(self, utility=None, substation_label=None, show_ratings=True,
                 meter_label=None):
        self.utility = utility or style.DEFAULT_UTILITY
        # utility meter box under the incoming cable; '' draws none
        self.meter_label = style.DEFAULT_METER if meter_label is None else meter_label
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
            self.incomer_offset = _clear_of_ways(
                max(style.MAIN_INCOMER_FROM_LEFT, block + symbols.MAIN_LAMPS_LEFT + 3.0),
                first, n)
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
            # (way numbers sit just under the busbar)
            below_bus = (1.0 + style.TEXT_BOARD_NAME * style.LINE_SPACING +
                         text_height(self.info_text, style.TEXT_BOARD_INFO) + 1.8 +
                         style.TEXT_WAY * style.LINE_SPACING)
            self.height = max(style.BOARD_HEIGHT, below_bus + self.bus_below_top)
            # Incomer to the right of the name/info block in the corner.
            block = max(text_width(self.name_text, style.TEXT_BOARD_NAME),
                        text_width(self.info_text, style.TEXT_BOARD_INFO)) + 1.5
            self.incomer_offset = _clear_of_ways(max(span / 2, block + 2.0), first, n)
            # The load table sits bottom right, clear of the incomer label.
            self.width = max(style.BOARD_MIN_WIDTH, span, self.incomer_offset + 12.0,
                             self.incomer_offset + 9.0 + table_w)
        self.way_offsets = [first + i * style.WAY_PITCH for i in range(n)]
        self.left = 0.0
        self.bottom = 0.0
        self.band = 0
        self.tier = 0
        self.remote_ways = set()   # DB ways drawn on a higher floor
        self.riser_blocks = []     # RiserBlock fed from this board
        self.riser_height = 0.0    # their height above the box top
        self.on_riser = None       # RiserBlock this board is drawn on
        self.below = 0.0           # drawing under the box (generator + ATS)
        self.gen_drop = 0.0        # box bottom -> ATS top
        gen = board.generator
        if gen is not None:
            text = "\n".join(split_cable(gen.cable))
            self.gen_drop = max(style.GEN_BOARD_TO_ATS,
                                symbols.vertical_length(text, style.TEXT_RATING) + 4.0)
            self.below = self.gen_drop + style.ATS_SIZE + symbols.generator_height()

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
        if pt.kind == ATS:
            return self.pt_bottom(pt) + style.ATS_SIZE
        return self.pt_bottom(pt) + style.UPS_HEIGHT

    def pt_output_y(self, pt):
        if pt.kind == TRANSFORMER and len(pt.outputs) > 1:
            return self.pt_body_top(pt) + 1.5
        return self.pt_body_top(pt)

    def ups_output_x(self, pt, board):
        n = len(pt.outputs)
        i = pt.outputs.index(board)
        if pt.kind in (TRANSFORMER, ATS):
            return self.pt_center(pt) + (i - (n - 1) / 2) * 3.0
        left, right = self.ups_span(pt)
        return left + (right - left) * (i + 1) / (n + 1)

    def db_height(self):
        """One height for all the DB boxes on the board, so they line up."""
        return max([symbols.db_box_height(w.name, w.loads()) for w in self.board.ways
                    if w.kind == DB_BOX and w not in self.remote_ways] or [0.0])

    def extent_right(self):
        """Right of the board and of the risers drawn above it."""
        right = max([self.right] + [b.right() for b in self.riser_blocks])
        gen = self.board.generator
        if gen is not None:
            info = [gen.ats.name] + gen.ats.info()
            right = max(right,
                        self.incomer_x + 1.4 + symbols.generator_width(gen.gen_cable, gen.lines()),
                        self.incomer_x + style.ATS_SIZE / 2 + 1.0 +
                        max(text_width(l, style.TEXT_ATS) for l in info))
        return right

    def content_height(self):
        """Height of everything drawn above the box top."""
        return max(self.ways_height(), self.riser_height)

    def ways_height(self):
        h = style.SPARE_HEIGHT + 8.0
        for w in self.board.ways:
            text = _rating_text(w)
            if text:
                # cable text on a riser must end below the next floor line
                h = max(h, style.RATING_START + style.RATING_CLEAR +
                        symbols.vertical_length(text, style.TEXT_RATING) * style.FLOOR_LABEL_SLACK)
            if w.kind == DB_BOX:
                h = max(h, style.TERMINAL_BASE + symbols.db_box_height(w.name, w.loads()))
            elif w.kind == ISOLATOR:
                h = max(h, style.TERMINAL_BASE + style.ISOLATOR_HEIGHT + style.ISOLATOR_HOOK +
                        0.8 + symbols.isolator_label_length(w.name, w.loads()[0]))
            elif w.kind == SPARE:
                h = max(h, style.SPARE_HEIGHT + 0.8 + symbols.vertical_length("SPARE", style.TEXT_SPARE))
            elif w.kind == TO_UPS:
                h = max(h, style.UPS_ABOVE_BOARD + style.UPS_HEIGHT + 4.0,
                        style.UPS_ABOVE_BOARD + 3.4 * style.PT_TRANSFORMER_RADIUS + 4.0,
                        style.UPS_ABOVE_BOARD + style.ATS_SIZE + 4.0,
                        style.UPS_ABOVE_BOARD + 1.0 + symbols.vertical_length(w.name, style.TEXT_LOAD))
            elif w.kind == PFC:
                h = max(h, style.PFC_ABOVE_BOARD + style.PFC_SIZE + 2.0 +
                        symbols.vertical_length(symbols.pfc_label(), style.TEXT_LOAD))
        return h


def _clear_of_ways(offset, first, n):
    """The incomer's offset moved half a way to the right when it would
    sit on a way's line (the way's riser would read as the incomer)."""
    for i in range(n):
        if abs(first + i * style.WAY_PITCH - offset) < style.WAY_PITCH / 4:
            return first + (i + 0.5) * style.WAY_PITCH
    return offset


class BoxGeom(object):
    """A DB box on its own floor: a DB on a higher floor than its board, fed
    by a riser (like UDB-FF-01 from USMDB-GF-M), or a DB fed from nothing in
    the model (equipment, no way)."""

    width = 4.0
    incomer_offset = 2.0

    def __init__(self, way=None, equipment=None):
        self.way = way
        self.equipment = equipment
        self.box_height = 0.0   # shared by the DB boxes on its floor (set by layout)
        self.left = 0.0
        self.bottom = 0.0       # board bottom of its row
        self.band = 0
        self.tier = 0

    @property
    def key(self):
        if self.way is None:
            return "db:%s" % self.equipment.id
        return "box:%s" % self.way.circuit.id

    @property
    def name(self):
        return self.way.name if self.way is not None else self.equipment.name

    def loads(self):
        if self.way is not None:
            return self.way.loads()
        return self.equipment.connected_kw, self.equipment.demand_kw

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
        return max(symbols.db_box_height(self.name, self.loads()), self.box_height)


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


class RiserBlock(object):
    """A bus bar riser drawn above the way feeding it. Heights are worked
    out relative to the bar bottom; x follows the way."""

    def __init__(self, riser, source, geoms):
        self.riser = riser
        self.source = source           # BoardGeom of the board feeding it
        self.label = riser.label()
        self.bottom = 0.0              # bar bottom (set after the rows are placed)
        self.rel_bottom = 0.0          # bar bottom above the source's box top
        self.items = []                # (tap, tap y, BoardGeom or None, box lines)
        boxes = [symbols.typical_box_lines(t.board.name, t.typical_of, t.board.equipment.level_name)
                 for t in riser.taps if t.is_typical]
        self.box_width = max([symbols.typical_box_size(l)[0] for l in boxes] or [0.0])
        y = style.RISER_FIRST_TAP
        for t in riser.taps:
            if t.is_typical:
                lines = symbols.typical_box_lines(t.board.name, t.typical_of,
                                                  t.board.equipment.level_name)
                h = symbols.typical_box_size(lines)[1]
                self.items.append((t, y + h / 2, None, lines))
                y += max(style.TAP_PITCH, h + 4.0)
            else:
                g = geoms[t.board.id]
                g.on_riser = self
                cable = t.cable_lines()
                y_tap = y + len(cable) * style.TEXT_RATING * style.LINE_SPACING + 1.0
                self.items.append((t, y_tap, g, cable))
                g.tap_y = y_tap
                y = (y_tap + style.TAP_TO_BOARD + g.height + g.content_height() +
                     style.TAP_BOARD_STACK)
        self.height = max(y + style.RISER_TOP_MARGIN, symbols.riser_label_length(self.label))

    @property
    def x(self):
        return self.source.way_x(self.riser.way)

    @property
    def top(self):
        return self.bottom + self.height

    def unit_right(self):
        return self.x + style.RISER_BAR_WIDTH / 2 + style.TAP_UNIT_W

    def box_left(self):
        return self.unit_right() + style.TAP_LINE

    def boards_left(self):
        if self.box_width:
            return self.box_left() + self.box_width + style.TAP_BOARD_GAP
        return self.unit_right() + style.TAP_LINE

    def right(self):
        r = self.box_left() + self.box_width
        for _, _, g, _ in self.items:
            if g is not None:
                r = max(r, self.boards_left() + g.width)
        return r

    def place_x(self):
        for _, _, g, _ in self.items:
            if g is not None:
                g.left = self.boards_left()

    def place_y(self):
        self.bottom = self.source.top + self.rel_bottom
        for t, y_tap, g, _ in self.items:
            if g is not None:
                g.bottom = self.bottom + y_tap + style.TAP_TO_BOARD


def _riser_blocks(schematic, geoms):
    """RiserBlocks on the boards feeding them, stacked above their ways:
    the rightmost riser lowest, so no tap-off crosses another bar."""
    blocks = []
    for riser in getattr(schematic, "risers", []):
        source = geoms.get(riser.source.id)
        if source is None:
            continue
        block = RiserBlock(riser, source, geoms)
        source.riser_blocks.append(block)
        blocks.append(block)
    for g in set(b.source for b in blocks):
        g.riser_blocks.sort(key=lambda b: -g.board.ways.index(b.riser.way))
        y = g.ways_height() + style.RISER_ABOVE_CONTENT
        for b in g.riser_blocks:
            b.rel_bottom = y
            y += b.height + style.RISER_GAP
        g.riser_height = y
    return blocks


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

    blocks = _riser_blocks(schematic, geoms)
    band_names, boxes = _assign_rows(schematic, geoms)
    for box in boxes:
        geoms[box.key] = box
    # DB boxes on one floor line up: one height for all of them
    tallest = {}
    for box in boxes:
        tallest[box.row] = max(tallest.get(box.row, 0.0),
                               symbols.db_box_height(box.name, box.loads()))
    for box in boxes:
        box.box_height = tallest[box.row]
    feeds = _collect_feeds(schematic, geoms, boxes)
    rows = sorted(set(g.row for g in geoms.values()))
    _place_x(schematic, geoms, feeds, rows)
    floor_ys, row_base = _best_route(geoms, feeds, rows)
    for block in blocks:
        block.place_y()

    d = Drawing()
    for g in geoms.values():
        if isinstance(g, BoardGeom):
            _draw_board(d, g, settings)
    for f in feeds:
        _draw_feed(d, f, row_base)
    for block in blocks:
        _draw_riser(d, block)
    for box in boxes:
        if box.way is None:
            symbols.db_box(d, box.incomer_x, box.feed_y, box.name, box.loads(), box.box_height)
    for root in schematic.roots:
        if root.generator is not None:
            _draw_generator(d, geoms, geoms[root.id])
        elif root.is_main:
            _draw_source(d, geoms[root.id], floor_ys[SUBSTATION_BAND], settings)

    x0, _, x1, _ = d.bounds()
    bands = []
    for band, y in sorted(floor_ys.items()):
        label = settings.substation_label if band == SUBSTATION_BAND else band_names[band]
        bands.append((label, y))
    # floor labels sit left of every board, so no board or cable text is drawn over them
    widest = max([text_width(label, style.TEXT_FLOOR_LABEL) for label, _ in bands if label] or [0])
    label_x = min(x0 - style.FLOOR_MARGIN, x0 - style.FLOOR_LABEL_GAP - widest * style.FLOOR_LABEL_SLACK)
    for label, y in bands:
        d.dashed_line(label_x, x1 + style.FLOOR_MARGIN, y, style.FLOOR_DASH, style.FLOOR_GAP)
        if label:
            d.text(label_x, y + 1.5, label, style.TEXT_FLOOR_LABEL, align=LEFT, valign=BOTTOM)
    return Layout(d, geoms, bands, feeds)


# ---------------------------------------------------------------- rows

def _assign_rows(schematic, geoms):
    """Band = floor (by level elevation), tier = stacking within a floor."""
    levels = {}
    for b in schematic.boards():
        if not b.is_main and geoms[b.id].on_riser is None:
            e = b.equipment
            levels.setdefault(e.level_name, e.level_elevation)
        for w in b.ways:
            if w.kind == DB_BOX and w.target is not None:
                levels.setdefault(w.target.level_name, w.target.level_elevation)
    for e in schematic.loose_dbs:
        levels.setdefault(e.level_name, e.level_elevation)
    ordered = sorted(levels.items(), key=lambda kv: (kv[1], kv[0]))
    band_of_level = dict((name, i) for i, (name, _) in enumerate(ordered))
    band_names = dict((i, name.upper()) for i, (name, _) in enumerate(ordered))

    def visit(board, parent_geom):
        g = geoms[board.id]
        if board.is_main or g.on_riser is not None or board.generator is not None:
            # a board on a bus bar riser is drawn beside it, above its supply
            g.band, g.tier = SUBSTATION_BAND, 0
        elif parent_geom is None:
            g.band, g.tier = band_of_level[board.equipment.level_name], 0
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
    for g in list(geoms.values()):
        if g.on_riser is not None:
            visit(g.board, None)

    boxes = []
    for b in schematic.boards():
        g = geoms[b.id]
        for w in b.ways:
            if w.kind != DB_BOX or w.target is None or g.on_riser is not None:
                continue
            band = band_of_level[w.target.level_name]
            if band > g.band and not (g.band == SUBSTATION_BAND and band == 0):
                box = BoxGeom(w)
                box.band, box.tier = band, 0
                boxes.append(box)
                g.remote_ways.add(w)
    for e in schematic.loose_dbs:
        box = BoxGeom(equipment=e)
        box.band, box.tier = band_of_level[e.level_name], 0
        boxes.append(box)
    return band_names, boxes


def _collect_feeds(schematic, geoms, boxes):
    feeds = []
    for box in boxes:
        if box.way is None:
            continue
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
        in_row = [g for g in geoms.values() if g.row == row and not _on_riser(g)]
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
            right = g.extent_right() if isinstance(g, BoardGeom) else g.right
            cursor = right + (gap if row[0] != SUBSTATION_BAND else 45.0)
        for g in in_row:
            for block in getattr(g, "riser_blocks", []):
                block.place_x()


def _route(geoms, feeds, rows, incomer_side=True):
    """Plan each riser: where it has to jog sideways.

    Row by row (bottom up), every riser in the row's jog zone (just under
    its boards) keeps its left-to-right order, so no two cross where it can
    be helped: a riser ending in the row jogs to its board's incomer; a
    riser passing through moves into a gap between the row's boards (lanes
    RISER_LANE apart), going round a board in its way on the side of the
    board's incomer it comes up on (incomer_side) or the side nearer its
    destination. Returns {row: number of jogs}.
    """
    clearance = style.RISER_CLEARANCE
    margin = style.RISER_MIN_CLEAR      # closest a riser may pass a board
    lane = style.RISER_LANE
    by_row = {}
    for g in geoms.values():
        if not _on_riser(g):
            by_row.setdefault(g.row, []).append(g)
    fed = set(f.target.key for f in feeds)
    xs = {}
    for f in feeds:
        f.jogs = []
        xs[f] = f.source_x()
    inf = float("inf")
    for row in rows:
        present = [f for f in feeds if f.source.row < row <= f.target.row]
        if not present:
            continue
        # blocked spans of the row's boards, merged; gaps between them
        spans = []
        for g in sorted(by_row.get(row, []), key=lambda g: g.left):
            lo, hi = g.left - margin, g.right + margin
            if spans and lo <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], hi)
                spans[-1][2].append(g)
            else:
                spans.append([lo, hi, [g]])
        gaps = [(-inf if k == 0 else spans[k - 1][1], spans[k][0] if k < len(spans) else inf)
                for k in range(len(spans) + 1)]

        def gap_of(x):
            for k, (a, b) in enumerate(gaps):
                if a - 1e-6 <= x <= b + 1e-6:
                    return k
            return None

        def first_gap(k, lo):
            for j in range(k, len(gaps)):
                if gaps[j][1] >= lo:
                    return j
            return len(gaps) - 1

        present.sort(key=lambda f: (xs[f], f.target.incomer_x))
        entries = []            # [feed, fixed x or None, gap, wanted x]
        lo = -inf
        for f in present:
            x = xs[f]
            if f.target.row == row:
                t = f.target.incomer_x
                entries.append([f, t, None, t])
                lo = max(lo, t + lane)
                continue
            k = gap_of(x)
            if k is not None:
                j = k if gaps[k][1] >= lo else first_gap(k + 1, lo)
            else:
                # under a board: go round it
                s_ = next(n for n, sp in enumerate(spans) if sp[0] < x < sp[1])
                board = min(spans[s_][2], key=lambda g: abs(g.incomer_x - x))
                target_x = f.target.incomer_x
                if incomer_side and board.key in fed:
                    left = x < board.incomer_x
                else:
                    left = abs(spans[s_][0] - target_x) <= abs(spans[s_][1] - target_x)
                if left and gaps[s_][1] >= lo:
                    j = s_          # the gap left of the board
                else:
                    j = first_gap(s_ + 1, lo)
            a, b = gaps[j]
            if a <= x <= b:
                want = x
            elif x > b:         # round the board on its right: clear of it if there is room
                want = max(a, b - (clearance - margin))
            else:
                want = min(b, a + (clearance - margin))
            entries.append([f, None, j, want])
            lo = max(lo, a)
        # positions: in order, RISER_LANE apart, inside their gaps
        pos = []
        prev = -inf
        for f, fixed, j, want in entries:
            if fixed is not None:
                p = fixed
            else:
                p = max(want, gaps[j][0], prev + lane)
            pos.append(p)
            prev = p
        nxt = inf
        for n in range(len(entries) - 1, -1, -1):
            f, fixed, j, want = entries[n]
            if fixed is None:
                low = gaps[j][0] if n == 0 else max(gaps[j][0], pos[n - 1] + lane)
                p = min(pos[n], nxt - lane)
                # never into a board: a gap too narrow for its risers lets them cross
                pos[n] = min(max(p, low), gaps[j][1])
            nxt = pos[n]
        for (f, fixed, j, want), p in zip(entries, pos):
            if abs(p - xs[f]) > 1e-6:
                f.jogs.append([row, xs[f], p, 0])
                xs[f] = p
    per_row = {}
    for f in feeds:
        for jog in f.jogs:
            per_row.setdefault(jog[0], []).append(jog)
    for row, jogs in per_row.items():
        for i, jog in enumerate(_order_jogs(jogs)):
            jog[3] = i
    return dict((row, len(jogs)) for row, jogs in per_row.items())


_ROUTINGS = ((True,), (False,))


def _best_route(geoms, feeds, rows):
    """Route the risers each way in _ROUTINGS and keep the one with the
    fewest lines crossing (the first on a tie). Returns _place_y's result."""
    best = None
    for n, args in enumerate(_ROUTINGS):
        jog_counts = _route(geoms, feeds, rows, *args)
        placed = _place_y(geoms, rows, jog_counts)
        count = _count_crossings([_feed_points(f, placed[1]) for f in feeds])
        if best is None or count < best[0]:
            best = (count, n)
        if count == 0:
            return placed
    if best[1] == n:
        return placed
    jog_counts = _route(geoms, feeds, rows, *_ROUTINGS[best[1]])
    return _place_y(geoms, rows, jog_counts)


def _feed_points(f, row_base):
    points = [(f.source_x(), f.source_y())]
    for row, x0, x1, track in f.jogs:
        y = row_base[row] - style.JOG_FIRST - track * style.JOG_TRACK
        points += [(x0, y), (x1, y)]
    points.append((f.target.incomer_x, f.target.feed_y))
    return points


def _count_crossings(polylines):
    """Horizontal segments of one riser crossing vertical segments of another."""
    hs, vs = [], []
    for i, pts in enumerate(polylines):
        for a, b in zip(pts, pts[1:]):
            if abs(a[1] - b[1]) < 1e-6 and abs(a[0] - b[0]) > 1e-6:
                hs.append((i, min(a[0], b[0]), max(a[0], b[0]), a[1]))
            elif abs(a[0] - b[0]) < 1e-6:
                vs.append((i, a[0], min(a[1], b[1]), max(a[1], b[1])))
    count = 0
    for i, x0, x1, y in hs:
        for j, x, y0, y1 in vs:
            if i != j and x0 + 1e-6 < x < x1 - 1e-6 and y0 + 1e-6 < y < y1 - 1e-6:
                count += 1
    return count


def _order_jogs(jogs):
    """Jogs of one row, top track first, with as few lines crossing
    another jog's riser as can be: a jog over the riser coming up to
    another jog (its from x) goes above that jog (the riser stops below
    it); over the riser leaving another jog upwards (its to x) it goes
    below it. Ties keep the old rule: longer jogs lower down."""
    def spans(j, x):
        lo, hi = min(j[1], j[2]), max(j[1], j[2])
        return lo + 1e-6 < x < hi - 1e-6

    n = len(jogs)
    # cost[i][k]: crossings when jog i is above jog k
    cost = [[0] * n for _ in range(n)]
    for i in range(n):
        for k in range(n):
            if i != k:
                cost[i][k] = (spans(jogs[i], jogs[k][2]) +   # k's riser up, through i
                              spans(jogs[k], jogs[i][1]))    # i's riser from below, through k
    start = sorted(range(n), key=lambda i: (min(jogs[i][1], jogs[i][2]),
                                            -abs(jogs[i][2] - jogs[i][1])))

    def total(order):
        return sum(cost[a][b] for x, a in enumerate(order) for b in order[x + 1:])

    if n <= 6:
        import itertools
        best = min(itertools.permutations(start), key=total)   # first best: ties keep start
        return [jogs[i] for i in best]
    order = list(start)
    improved = True
    while improved:
        improved = False
        for x in range(n - 1):
            a, b = order[x], order[x + 1]
            if cost[b][a] < cost[a][b]:
                order[x], order[x + 1] = b, a
                improved = True
    return [jogs[i] for i in order]


def _place_y(geoms, rows, jog_counts):
    """Stack rows bottom-up; returns ({band: floor y}, {row: board bottom})."""
    floor_ys, row_base = {}, {}
    y = 0.0
    for row in rows:
        in_row = [g for g in geoms.values() if g.row == row and not _on_riser(g)]
        n = jog_counts.get(row, 0)
        if row[1] == 0:
            floor_ys[row[0]] = y
        if row[0] == SUBSTATION_BAND:
            bottom = y + max([style.SUBSTATION_STACK] +
                             [g.below + 4.0 for g in in_row if isinstance(g, BoardGeom)])
        else:
            bottom = y + style.JOG_BOTTOM_MARGIN + max(n, 1) * style.JOG_TRACK + style.JOG_FIRST
        row_base[row] = bottom
        top = bottom
        for g in in_row:
            g.bottom = bottom
            top = max(top, g.top + g.content_height())
        y = top + style.ROW_TOP_MARGIN
    return floor_ys, row_base


def _on_riser(g):
    return getattr(g, "on_riser", None) is not None


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
                "%s, %s WAYS" % (e.form or style.DEFAULT_FORM, board.way_count())]
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
    # the busbar runs the width of the board (office style)
    bus_l = min(xs + [g.incomer_x, g.left + style.BUS_END_MARGIN + 3.0]) - 3.0
    bus_r = max(xs + [g.incomer_x, g.right - style.BUS_END_MARGIN - 3.0]) + 3.0
    d.line(bus_l, g.bus_y, bus_r, g.bus_y)

    for w, x in zip(b.ways, xs):
        y_arc = g.bus_y + (style.BREAKER_ABOVE_BUS if not b.is_main else 4.0)
        d.line(x, g.bus_y, x, y_arc)
        top_arc = symbols.breaker(d, x, y_arc)
        d.line(x, top_arc, x, g.top)
        if w.label and b.is_main:
            d.text(x - 0.4, g.bus_y + 0.4, w.label, style.TEXT_WAY, align=RIGHT, valign=BOTTOM)
        elif w.label:
            # under the busbar: clear of the breaker text of the way to its left
            d.text(x - 0.4, g.bus_y - 0.4, w.label, style.TEXT_WAY, align=RIGHT, valign=TOP)
        symbols.breaker_label(d, x + style.BREAKER_RADIUS + 0.3, y_arc + style.BREAKER_RADIUS,
                              w.breaker_lines(), style.TEXT_WAY)
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
        symbols.breaker_label(d, xi + 2.0, y_arc + style.BREAKER_RADIUS,
                              b.equipment.incomer_lines(), style.TEXT_WAY)
        d.text(g.left + 1.0, g.bottom + 1.0, g.name_text, style.TEXT_BOARD_NAME,
               align=LEFT, valign=BOTTOM)
        d.text(g.left + 1.5, g.bottom + 1.0 + style.TEXT_BOARD_NAME * style.LINE_SPACING,
               g.info_text, style.TEXT_BOARD_INFO, align=LEFT, valign=BOTTOM)


def _draw_pass_through(d, g, pt):
    y0 = g.pt_bottom(pt)
    if pt.kind == ATS:
        xs = g.pt_inputs(pt)
        cx = g.pt_center(pt)
        if len(xs) > 1:
            d.line(min(xs), y0 - 1.5, max(xs), y0 - 1.5)
            d.line(cx, y0 - 1.5, cx, y0)
        symbols.ats(d, cx, y0, pt.equipment.name, symbols.ats_info(pt.equipment))
        return
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


def _isolator_rating(w):
    """'300A,4P': the isolator takes its breaker's rating; 4P on a
    three-phase way (TPN), 2P on a single-phase one."""
    trip = w.trip()
    if trip is None:
        return ""
    try:
        poles = int(w.circuit.poles)
    except (AttributeError, TypeError, ValueError):
        poles = 3
    return "%sA,%s" % (trim_number(trip, 1), "4P" if poles >= 3 else "2P")


def _rating_text(w):
    """Breaker rating and cable text along a way, wrapped to its room."""
    lines = w.rating_lines()
    if not lines:
        return ""
    room = _RATING_ROOM.get(w.kind, style.TERMINAL_BASE) - style.RATING_START - 1.5
    return wrap("\n".join(lines), style.TEXT_RATING, room)


def _draw_way_end(d, g, w, x, settings):
    t = g.top
    if w in g.remote_ways:
        pass  # riser + box drawn by _draw_feed
    elif w.kind == DB_BOX:
        d.line(x, t, x, t + style.TERMINAL_BASE)
        symbols.db_box(d, x, t + style.TERMINAL_BASE, w.name, w.loads(), g.db_height())
    elif w.kind == ISOLATOR:
        d.line(x, t, x, t + style.TERMINAL_BASE)
        symbols.isolator(d, x, t + style.TERMINAL_BASE, w.name, _isolator_rating(w),
                         w.loads()[0])
    elif w.kind == SPARE:
        d.line(x, t, x, t + style.SPARE_HEIGHT)
        symbols.spare(d, x, t + style.SPARE_HEIGHT, w.name)
    elif w.kind == PFC:
        y0 = t + style.PFC_ABOVE_BOARD
        d.line(x, t, x, y0)
        symbols.pfc(d, x, y0)
    elif w.kind == TO_UPS:
        pt = next(p for p in g.board.pass_throughs if w in p.input_ways)
        joined = pt.kind in (TRANSFORMER, ATS) and len(pt.input_ways) > 1
        d.line(x, t, x, g.pt_bottom(pt) - (1.5 if joined else 0.0))
    # FEEDER: the riser is drawn by _draw_feed.

    if settings.show_ratings:
        text = _rating_text(w)
        if text:
            # Reading up, centred on the way line (the office position): the
            # first line (cable size) left of it, the rest (earth, L, V.D)
            # right of it. A single line goes on the right.
            first, _, rest = text.partition("\n")
            y0 = t + style.RATING_START
            if rest:
                d.text(x - 0.3, y0, first, style.TEXT_RATING, align=LEFT, valign=BOTTOM,
                       rotation=symbols.VERTICAL)
            d.text(x + 0.3, y0, rest or first, style.TEXT_RATING, align=LEFT, valign=TOP,
                   rotation=symbols.VERTICAL)


def _draw_feed(d, f, row_base):
    xt, yt = f.target.incomer_x, f.target.feed_y
    if isinstance(f.target, BoxGeom):
        symbols.db_box(d, xt, yt, f.target.name, f.target.loads(), f.target.box_height)
    points = _feed_points(f, row_base)
    f.points = points
    d.polyline(points)


def _draw_source(d, g, floor_y, settings):
    """Everything under a main board, as the office SLD: incoming cable
    (one line), utility meter, transformer with its own earth, then a
    straight line down to FROM <utility>."""
    b = g.board
    x = g.incomer_x
    y = g.bottom
    cable = b.equipment.incoming_cable
    y_cable = y - 3.5
    d.line(x, y, x, y_cable + 0.6)
    symbols.cable_mark(d, x, y_cable, _cable_label(cable) if cable else None)
    y = y_cable - 0.6
    if b.ats is not None:
        # fed through a transfer switch (its supplies are not in the model)
        y_ats = y - 3.0 - style.ATS_SIZE
        d.line(x, y, x, y_ats + style.ATS_SIZE)
        symbols.ats(d, x, y_ats, b.ats.name, symbols.ats_info(b.ats))
        return
    if settings.meter_label:
        trip = b.equipment._incomer()[0]
        ratio = "%sA/5A" % trim_number(trip, 0) if trip else ""
        y_meter = y - 2.0
        d.line(x, y, x, y_meter)
        y = symbols.utility_meter(d, x, y_meter, settings.meter_label, ratio)
    if b.transformer is not None:
        tr = b.transformer
        y_tr = y - 3.0
        d.line(x, y, x, y_tr)
        y = symbols.transformer(d, x, y_tr, tr.name, tr.description)
    end_y = min(y - 4.0, floor_y - 5.0)
    d.line(x, y, x, end_y)
    d.text(x, end_y - 1.0, "FROM %s" % settings.utility, style.TEXT_SUPPLY,
           align=CENTER, valign=TOP)


def _draw_generator(d, geoms, g):
    """Under a board with a generator (office SLD): its cable down to the
    ATS, the normal supply into the ATS from the left (from the way that
    fed the board), the generator at the bottom."""
    gen = g.board.generator
    x = g.incomer_x
    y_top = g.bottom - g.gen_drop
    y0 = y_top - style.ATS_SIZE
    d.line(x, g.bottom, x, y_top)
    lines = split_cable(gen.cable)
    if lines:
        first, rest = lines[0], "\n".join(lines[1:])
        ys = y_top + 1.5
        if rest:
            d.text(x - 0.3, ys, first, style.TEXT_RATING, align=LEFT, valign=BOTTOM,
                   rotation=symbols.VERTICAL)
        d.text(x + 0.3, ys, rest or first, style.TEXT_RATING, align=LEFT, valign=TOP,
               rotation=symbols.VERTICAL)
    _, y_normal, x_standby = symbols.ats_standby(d, x, y0, gen.ats.name, gen.ats.info())
    symbols.generator(d, x_standby, y0, gen.gen_cable, gen.lines())

    x_in = x - style.ATS_SIZE / 2
    src = geoms.get(gen.normal_board.id) if gen.normal_board is not None else None
    if src is not None and src.band == SUBSTATION_BAND and gen.normal_way in src.board.ways:
        wx = src.way_x(gen.normal_way)
        y_h = src.top + src.content_height() + style.GEN_NORMAL_ABOVE
        x_v = src.extent_right() + style.GEN_NORMAL_GAP
        if x_v > x_in - 2.0:
            x_v = x_in - 2.0
        d.polyline([(wx, src.top), (wx, y_h), (x_v, y_h), (x_v, y_normal), (x_in, y_normal)])
        return
    if src is not None and gen.normal_way in src.board.ways:
        # the board feeding it is on a floor: its way ends 'TO ATS (board)'
        wx = src.way_x(gen.normal_way)
        y1 = src.top + style.TERMINAL_BASE
        d.line(wx, src.top, wx, y1)
        symbols.vertical_text(d, wx, y1 + 0.8, "TO ATS (%s)" % g.board.name, style.TEXT_LOAD)
    text = gen.normal_text or ("FROM %s" % gen.normal_board.name if gen.normal_board else "")
    x_end = x_in - 3.0 - max(text_width(t, style.TEXT_GEN_CABLE) for t in ("NORMAL SUPPLY", text))
    d.line(x_end, y_normal, x_in, y_normal)
    d.text(x_end, y_normal + 0.5, "NORMAL SUPPLY", style.TEXT_GEN_CABLE, align=LEFT, valign=BOTTOM)
    if text:
        d.text(x_end, y_normal - 0.5, text, style.TEXT_GEN_CABLE, align=LEFT, valign=TOP)


def _cable_label(cable):
    """'7 SC 630mm² Cu/XLPE/AWA/PVC' on one line (office SLD); a cable
    with an earth part has the earth on a second line."""
    return "\n".join(split_cable(cable))


def _draw_riser(d, block):
    """The way up to the bar, the bar, and each tap-off with its board."""
    x = block.x
    d.line(x, block.source.top, x, block.bottom)
    symbols.riser_bar(d, x, block.bottom, block.top, block.label)
    bar_r = x + style.RISER_BAR_WIDTH / 2
    for tap, y_tap, g, extra in block.items:
        y = block.bottom + y_tap
        x0 = symbols.tap_unit(d, bar_r, y, tap.rating_text())
        if g is None:
            d.line(x0, y, block.box_left(), y)
            symbols.typical_box(d, block.box_left(), y, extra, block.box_width)
            continue
        xi = g.incomer_x
        d.polyline([(x0, y), (xi, y), (xi, g.bottom)])
        if extra:
            # tap-off cable under the line, as the office SLD
            d.text(x0 + 1.5, y - 0.5, "\n".join(extra), style.TEXT_RATING, align=LEFT, valign=TOP)
