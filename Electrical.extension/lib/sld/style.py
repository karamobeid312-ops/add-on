# -*- coding: utf-8 -*-
"""Drawing standard for the LV schematic diagram.

Every size is in millimetres on paper; the diagram is drawn 1:1 so these
match the printed sheet. Values were measured from the office standard
drawing (2427 0EE 321 LV System Schematic Diagram). Edit here to change the
look of every generated diagram.
"""

# ---------------------------------------------------------------- text sizes
TEXT_FLOOR_LABEL = 4.0      # ROOF FLOOR, GROUND FLOOR ...
TEXT_BOARD_NAME = 2.5       # SMDB-RF-01
TEXT_BOARD_INFO = 1.5       # FORM 2b, 18 WAYS / LOCATION / @ FLOOR
TEXT_MAIN_NAME = 5.0        # MDB-1
TEXT_MAIN_INFO = 2.5        # FORM4-TYPE6 / LOCATION:LV ROOM
TEXT_WAY = 1.2              # way numbers and breaker ratings (40AT/100AF/MCCB)
TEXT_LOAD = 1.8             # load / DB names, SPARE
TEXT_RATING = 1.2           # breaker rating and cable along a way
TEXT_DB_LOAD = 1.2          # CL / DL beside a DB box
TEXT_LOAD_TABLE = 1.5       # connected / demand load table in a board
TEXT_SMALL = 1.5            # labels inside the main board (ACB, SPD...)
TEXT_TRANSFORMER_NAME = 3.5
TEXT_TRANSFORMER_INFO = 2.0
TEXT_CABLE = 2.0            # incoming / MV cable labels
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
RISER_CLEARANCE = 5.0       # riser jogs this far clear of a board it passes

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

# ---------------------------------------------------------------- loads
TERMINAL_BASE = 36.5        # board top -> bottom of DB box / isolator
DB_BOX_WIDTH = 2.6
DB_BOX_HEIGHT = 18.0
ISOLATOR_WIDTH = 2.2
ISOLATOR_HEIGHT = 4.4
ISOLATOR_HOOK = 2.0
SPARE_HEIGHT = 6.6          # board top -> end of a SPARE way
UPS_ABOVE_BOARD = 30.0      # board top -> bottom of UPS / transformer box
UPS_HEIGHT = 3.4
UPS_MARGIN = 3.5            # UPS box overhang beyond its input ways
PT_TRANSFORMER_RADIUS = 2.0 # transformer fed from a board (between floors)
PFC_SIZE = 5.0
PFC_ABOVE_BOARD = 22.0      # board top -> bottom vertex of the PFC symbol
PFC_LABEL = "POWER FACTOR\nCORRECTION"
RATING_START = 2.0          # board top -> start of rating/cable text

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
