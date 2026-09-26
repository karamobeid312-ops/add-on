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
TEXT_MAIN_INFO = 3.0        # FORM4-TYPE6 / LOCATION:LV ROOM
TEXT_WAY = 1.5              # way numbers and "MCCB"
TEXT_LOAD = 1.8             # load / DB names, SPARE
TEXT_RATING = 1.5           # breaker rating and cable along a way
TEXT_SMALL = 1.5            # labels inside the main board (ACB, SPD...)
TEXT_TRANSFORMER_NAME = 3.5
TEXT_TRANSFORMER_INFO = 2.0
TEXT_CABLE = 2.0            # incoming / MV cable labels
TEXT_FONT = "Arial"

# Approximate character width as a fraction of text height (for sizing).
CHAR_WIDTH = 0.72

# ---------------------------------------------------------------- floors
FLOOR_DASH = 15.0
FLOOR_GAP = 5.0
FLOOR_MARGIN = 15.0         # dashed line overhang left/right of the diagram
SUBSTATION_LABEL = "SUBSTATION"

# ---------------------------------------------------------------- boards
WAY_PITCH = 8.0             # distance between outgoing ways
BOARD_MARGIN = 7.0          # box edge -> first/last way
BOARD_MIN_WIDTH = 60.0
BOARD_HEIGHT = 21.0
BUS_BELOW_TOP = 9.0         # box top -> busbar
BREAKER_ABOVE_BUS = 4.5     # busbar -> bottom of the breaker arc
BREAKER_RADIUS = 0.9
INCOMER_BREAKER_BELOW_BUS = 5.0
BOARD_GAP = 12.0            # min horizontal gap between boards in a row
RISER_CLEARANCE = 5.0       # riser jogs this far clear of a board it passes

# Equipment whose panel name matches is always drawn as a full board
# (with all its ways), even when it only feeds final loads.
BOARD_NAME_PATTERN = r"^[A-Z]{0,2}(MDB|MSB)"   # MDB, SMDB, USMDB, ESMDB, MSB...

DEFAULT_FORM = "FORM 2b"
DEFAULT_MAIN_FORM = "FORM4-TYPE6"
WAY_DEVICE = "MCCB"

# ---------------------------------------------------------------- main board
MAIN_MIN_WIDTH = 115.0
MAIN_HEIGHT = 42.0
MAIN_BUS_BELOW_TOP = 8.5
MAIN_INCOMER_FROM_LEFT = 50.0
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
UPS_ABOVE_BOARD = 26.0      # board top -> bottom of UPS box
UPS_HEIGHT = 3.4
UPS_MARGIN = 8.0            # UPS box overhang beyond its input ways
PFC_SIZE = 5.0
PFC_ABOVE_BOARD = 22.0      # board top -> bottom vertex of the PFC symbol
PFC_LABEL = "POWER FACTOR\nCORRECTION"
RATING_START = 2.0          # board top -> start of rating/cable text

# ---------------------------------------------------------------- rows / risers
ROW_TOP_MARGIN = 8.0        # highest content -> next row
JOG_FIRST = 4.0             # board bottom -> first jog track
JOG_TRACK = 2.5             # spacing between jog tracks
JOG_BOTTOM_MARGIN = 5.0     # lowest jog track -> row bottom
