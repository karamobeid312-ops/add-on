# -*- coding: utf-8 -*-
"""Drawing standard for the LV schematic diagram.

Every size is in millimetres on paper; the diagram is drawn 1:1 so these
match the printed sheet. Values were measured from the office standard
drawing (2427 0EE 321 LV System Schematic Diagram). Edit here to change the
look of every generated diagram.
"""

# ---------------------------------------------------------------- text sizes
TEXT_FLOOR_LABEL = 2.5      # ROOF FLOOR, GROUND FLOOR ...
TEXT_BOARD_NAME = 2.5       # SMDB-RF-01
TEXT_BOARD_INFO = 1.2       # FORM 2b, 18 WAYS / LOCATION / @ FLOOR
TEXT_MAIN_NAME = 3.0        # MDB-1
TEXT_MAIN_INFO = 1.5        # FORM4-TYPE6 / LOCATION:LV ROOM
TEXT_WAY = 1.2              # way numbers and breaker ratings (40AT/100AF/MCCB)
TEXT_LOAD = 1.8             # load / DB names
TEXT_SPARE = 1.2            # SPARE, the size of the cable text (office SLD)
TEXT_RATING = 1.2           # breaker rating and cable along a way
TEXT_DB_LOAD = 1.2          # CL / DL beside a DB box
TEXT_LOAD_TABLE = 1.2       # connected / demand load table in a board
TEXT_SMALL = 1.2            # labels inside the main board (ACB, SPD...)
TEXT_TRANSFORMER_NAME = 2.5
TEXT_TRANSFORMER_INFO = 1.5
TEXT_CABLE = 1.5            # incoming / MV cable labels
TEXT_SUPPLY = 2.5           # FROM TAQA under the transformer
TEXT_ISOLATOR = 1.5         # CL:135.0kW / FOR ELEC PUMP above an isolator
TEXT_ISOLATOR_NOTE = 0.9    # W.P beside the isolator
TEXT_RISER = 1.5            # 1000A TPN+E COPPER BUS BAR RISER-1 ... in the bar
TEXT_TAP = 1.5              # board name in a typical tap-off box
TEXT_TAP_INFO = 1.2         # DB SAME AS ... / @ FLOOR in the box, tap-off rating
TEXT_FONT = "Arial"

# Text height is the capital letter height (as Revit's Text Size); widths
# are estimated from Arial's character widths times this safety factor.
CHAR_WIDTH = 1.05
LINE_SPACING = 1.6          # baseline to baseline, as a multiple of height
# Revit text types created for the diagram use this Leader/Border Offset.
TEXT_BORDER_OFFSET = 0.3

# ---------------------------------------------------------------- floors
FLOOR_DASH = 15.0
FLOOR_GAP = 5.0
FLOOR_MARGIN = 15.0         # dashed line overhang left/right of the diagram
FLOOR_LABEL_GAP = 5.0       # floor label end -> leftmost board or text
FLOOR_LABEL_SLACK = 1.2     # Revit text runs wider than the estimate
SUBSTATION_LABEL = "SUBSTATION"

# ---------------------------------------------------------------- boards
WAY_PITCH = 9.0             # distance between outgoing ways
BOARD_MARGIN = 7.0          # box edge -> first/last way
BOARD_MIN_WIDTH = 60.0
BOARD_HEIGHT = 22.0
BUS_BELOW_TOP = 9.0         # box top -> busbar
BREAKER_ABOVE_BUS = 4.5     # busbar -> bottom of the breaker arc
BREAKER_RADIUS = 0.9
INCOMER_BREAKER_BELOW_BUS = 5.0
BOARD_GAP = 12.0            # min horizontal gap between boards in a row
BUS_END_MARGIN = 1.5        # busbar end -> board side
RISER_CLEARANCE = 5.0       # riser jogs this far clear of a board it passes
RISER_LANE = 2.5            # between risers jogging round the same side of a board

# Spare breakers added to every sub-main board: as many as fit between the
# minimum and maximum without going over the board's limit. Ways are counted
# as on the board: single-pole breakers on R, Y and B share one way.
MIN_SPARES = 2
MAX_SPARES = 3
MAX_WAYS = 18               # most circuit breakers (ways) on a sub-main board
SUB_MAIN_NAME_PATTERN = r"^[A-Z]{0,2}SM(DB|SB)"   # SMDB, USMDB, ESMDB, SMSB...

# Equipment whose panel name matches is always drawn as a full board
# (with all its ways), even when it only feeds final loads.
BOARD_NAME_PATTERN = r"^[A-Z]{0,2}(MDB|MSB)"   # MDB, SMDB, USMDB, ESMDB, MSB...

DEFAULT_FORM = "FORM 2b"
DEFAULT_MAIN_FORM = "FORM4-TYPE6"
WAY_DEVICE = "MCCB"
# Standard frame sizes (AF): a breaker is shown on the smallest frame that
# takes its trip rating (AT), e.g. 40AT -> 100AF, 125AT -> 160AF. 'SLD Frame'
# typed on a circuit or panel overrides it.
MCCB_FRAMES = (100, 160, 250, 400, 630, 800, 1000, 1250, 1600)
ACB_FRAMES = (800, 1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000, 6300)
ACB_FROM = 800              # main incomer below this (A) is an MCCB, not an ACB
# Device names read from Incomer_Type / Upstream_Protection_Type; switches
# have no trip rating and print as '100A / MCS'.
BREAKER_DEVICES = ("MCCB", "MCB", "ACB", "MCS", "RCBO", "RCCB", "ELCB", "FUSE",
                   "ISOLATOR", "SWITCH")
SWITCH_DEVICES = ("MCS", "ISOLATOR", "SWITCH")

# ---------------------------------------------------------------- main board
MAIN_MIN_WIDTH = 115.0
MAIN_HEIGHT = 42.0
MAIN_BUS_BELOW_TOP = 8.5
MAIN_INCOMER_FROM_LEFT = 68.0
MAIN_INCOMER_DEVICE = "ACB"
MAIN_CT_LABEL = "3NO"
MAIN_BUSBAR_FUSE = "BUSBAR MOUNTED\nFUSE @ 20A"
MAIN_LAMP_FUSE = "2A FUSE"
MAIN_LAMPS_LABEL = "INDICATOR LAMPS"
MAIN_EARTH_LABEL = u"R<1Ω"
MAIN_SPD_LABEL = "SPD"

# ---------------------------------------------------------------- transformer / source
SUBSTATION_STACK = 34.0     # substation floor line -> main board bottom
TRANSFORMER_RADIUS = 3.0
DEFAULT_UTILITY = "TAQA"
DEFAULT_METER = "ADDC METER"   # utility meter box under the incoming cable

# ---------------------------------------------------------------- loads
TERMINAL_BASE = 36.5        # board top -> bottom of DB box / isolator
DB_BOX_WIDTH = 2.6
DB_BOX_HEIGHT = 18.0
ISOLATOR_WIDTH = 2.2
ISOLATOR_HEIGHT = 4.4
ISOLATOR_HOOK = 2.0
ISOLATOR_NOTE = "W.P"       # beside every isolator (weatherproof); '' for none
SPARE_HEIGHT = 6.6          # board top -> end of a SPARE way
UPS_ABOVE_BOARD = 30.0      # board top -> bottom of UPS / transformer box
UPS_HEIGHT = 3.4
UPS_MARGIN = 3.5            # UPS box overhang beyond its input ways
PT_TRANSFORMER_RADIUS = 2.0 # transformer fed from a board (between floors)
PFC_SIZE = 5.0
PFC_ABOVE_BOARD = 22.0      # board top -> bottom vertex of the PFC symbol
PFC_LABEL = "POWER FACTOR\nCORRECTION"
RATING_START = 2.0          # board top -> start of rating/cable text
RATING_CLEAR = 3.0          # end of rating/cable text -> next row's floor line

# ---------------------------------------------------------------- load table
LOAD_TABLE_ROWS = ("CONNECTED LOAD", "DIVERSITY FACTOR", "DEMAND LOAD")
LOAD_TABLE_ROW = 2.6        # row height
LOAD_TABLE_PAD = 0.6        # text inset from the cell edges
LOAD_TABLE_MARGIN = 1.5     # table -> board edge

# ---------------------------------------------------------------- rows / risers
ROW_TOP_MARGIN = 8.0        # highest content -> next row
JOG_FIRST = 4.0             # board bottom -> first jog track
JOG_TRACK = 2.5             # spacing between jog tracks
JOG_BOTTOM_MARGIN = 5.0     # lowest jog track -> row bottom

# ---------------------------------------------------------------- bus bar riser
RISER_BAR_WIDTH = 3.0       # the bar, its label reading up inside
RISER_ABOVE_CONTENT = 4.0   # board's highest way content -> bottom of the bar
RISER_FIRST_TAP = 6.0       # bar bottom -> lowest tap-off
RISER_TOP_MARGIN = 4.0      # highest tap-off / board -> bar top
RISER_GAP = 6.0             # one riser's bar top -> next riser's bar bottom
TAP_PITCH = 10.0            # between typical tap-offs
TAP_UNIT_W = 2.8            # tap-off unit on the bar's side
TAP_UNIT_H = 1.4
TAP_LINE = 11.0             # tap-off unit -> typical box
TAP_BOX_PAD = 0.8
TAP_TO_BOARD = 5.0          # tap-off line -> bottom of a board drawn in full
TAP_BOARD_GAP = 8.0         # typical boxes -> boards drawn in full
TAP_BOARD_STACK = 6.0       # a full board's content -> next tap-off above
TYPICAL_TEXT = "DB SAME AS %s"

# ---------------------------------------------------------------- transfer switch (ATS)
ATS_SIZE = 6.0              # square box with the switch inside
TEXT_ATS = 1.8              # ATS name beside the box
TEXT_ATS_INFO = 1.2         # 630A,4P / LOCATION

# ---------------------------------------------------------------- standby generator (sld.generator)
GEN_RADIUS = 3.0            # the 'G' circle
TEXT_GEN_LETTER = 3.2
TEXT_GEN = 1.8              # G-01 PRIME GENERATOR / 0.4kV... / 300 kVA
TEXT_GEN_CABLE = 1.5        # generator cable above its line, earth cable
GEN_BOARD_TO_ATS = 10.0     # min line from the board down to the ATS (cable text on it)
GEN_BELOW_ATS = 9.0         # ATS bottom -> generator centre
GEN_FROM_ATS = 21.0         # min ATS standby contact -> generator circle
GEN_EARTH_1 = 22.0          # generator centre -> first earth pit
GEN_EARTH_2 = 28.0          # ... second earth pit
GEN_EARTH_DROP = 9.0        # generator centre -> earth pits
GEN_EARTH_TAIL = 22.0       # earth cable line right of the second pit
GEN_NORMAL_GAP = 6.0        # normal supply line right of the board feeding it
GEN_NORMAL_ABOVE = 3.0      # normal supply line above that board's content
