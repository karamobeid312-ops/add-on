# LV Schematic Diagram for Revit (pyRevit)

A [pyRevit](https://github.com/pyrevitlabs/pyRevit) extension that automatically
draws the **low voltage system schematic diagram** of a Revit model in the
office standard format (as drawing 2427 0EE 321): boards on their floors,
every outgoing way, UPS, main boards with transformer and supply.

![Preview of the Al Yasat sample](docs/layout-preview.png)

*Preview of the built-in Al Yasat sample (`tools/preview_svg.py`), no Revit needed.*

The repository also holds a **Fire Alarm** extension that places smoke and
heat detectors in the selected spaces, see [Fire alarm detectors](#fire-alarm-detectors).

## What gets drawn

| Item | How |
| --- | --- |
| **Floors** | One band per Revit level, dashed floor line and label (`ROOF FLOOR`, `GROUND FLOOR`...). Main boards go in the `SUBSTATION` band at the bottom. The diagram reads bottom to top. |
| **Boards** (MDB, SMDB, USMDB...) | Box with busbar, every outgoing way numbered 1, 2, 3... in slot order (on three-phase boards consecutive single-pole circuits share a way: R9, Y9, B9) with an `MCCB` breaker, incomer MCCB under the busbar, and `FORM 2b, 18 WAYS` / `LOCATION: ...` / `@ FLOOR` / board name. |
| **Main boards** | `FORM4-TYPE6`, `LOCATION: LV ROOM`, CT with 3 ammeters, indicator lamps, withdrawable ACB, busbar mounted fuse, SPD to earth `R<1Ω`, incoming cable, transformer, `MV CABLE FROM TAQA`, `FROM TAQA`. |
| **Final DBs** (LDB, PDB, DB-...) | Tall box with the name, at the end of the way. A DB on a higher floor than its board is drawn on its own floor, fed by a riser (like UDB-FF-01 from USMDB-GF-M). |
| **Equipment** (AHU, VRF, pumps, EV...) | Local isolator with the load name. |
| **Spare ways** | `SPARE`. |
| **PFC** | Capacitor bank symbol, `POWER FACTOR CORRECTION`. |
| **UPS** | Box across the ways that feed it; its output rises to the UPS board. |
| **Transformer fed from a board** | Transformer symbol on the way, its output rises to the panel it feeds (e.g. SWB → T-2A → PP-2A). |
| **Feeders between boards** | Risers straight up from the way, jogging around any board in the way and lining up under the fed board's incomer. |
| **Ratings** (optional) | Breaker rating and BS/IEC cable along each way, e.g. `63A TP` / `4Cx16mm² Cu/XLPE/PVC` / `+ 1Cx16mm² Cu/XLPE/PVC`. |

Buttons on the **SLD** tab → **Electrical** panel:

- **Generate SLD** – creates a new drafting view `LV Schematic Diagram`
  (`LV Schematic Diagram 2`, ... on later runs; earlier diagrams are never
  overwritten). The view is 1:1, so sizes match the printed sheet; place it
  on your A1 title block sheet.
- **SLD Settings** – utility name (`TAQA`), bottom band label (`SUBSTATION`),
  ratings on/off, and way numbering (ways in order, or Revit circuit numbers).

## How the model is read

| Drawing | Revit |
| --- | --- |
| Board / DB / main board | **Electrical Equipment**. Equipment that feeds other equipment, or whose name looks like a board (`MDB`, `SMDB`, `USMDB`, `MSB`...), is a board. Equipment with no supply is a main board. Everything else is a final DB. |
| Transformer | Electrical equipment whose family part type is *Transformer* (or family name contains `TRANSFORMER`). With no supply of its own it is drawn under the main board it feeds; fed from a board it is drawn on that board's way. |
| UPS | Electrical equipment whose family name contains `UPS`. |
| Floor | The equipment's **level**. |
| Location | The **room** the equipment is in (name + number). |
| Ways | Power circuits of the board, in slot order. Spare circuits → `SPARE`; spaces are skipped. |
| Load name | The circuit's **Load Name**. `PFC` / `POWER FACTOR` / `CAPACITOR` → PFC symbol. |
| Number of ways | *Max #1 Pole Breakers* ÷ 3 for three-phase boards. |

### Optional parameters

Add these as project or shared **Text** parameters to fine-tune the drawing.
Empty values are ignored.

| Category | Parameter | Example |
| --- | --- | --- |
| Electrical Equipment | `SLD Symbol` | `MAIN`, `BOARD`, `DB`, `UPS`, `TRANSFORMER` |
| Electrical Equipment | `SLD Form` | `FORM 2b`, `FORM4-TYPE6` |
| Electrical Equipment | `SLD Ways` | `18` |
| Electrical Equipment | `SLD Location` | `ELEC. ROOM GF-48` |
| Electrical Equipment | `SLD Description` | transformer text, one item per line: `11/0.4kV` `1000KVA` `OIL TYPE` `TRANSFORMER` |
| Electrical Equipment | `SLD Incoming Cable` | `7 SC 630mm² Cu/XLPE/AWA/PVC` |
| Electrical Circuits | `SLD Cable` | cable text printed exactly as typed |
| Electrical Circuits | `SLD Symbol` | `ISOLATOR`, `DB`, `SPARE`, `PFC` |

## Cable descriptions (BS / IEC)

Cables are generated from the circuit, e.g.
`4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC`:

| Part | Taken from the circuit |
| --- | --- |
| `4C` | Number of hot + neutral conductors |
| `4mm²` | First size in Revit's *Wire Size* (needs metric wire sizes) |
| `+ 1Cx4mm²` | Number of ground conductors and the last size in *Wire Size* (reduced earths are kept) |
| `Cu` / `Al` | Wire type material |
| `XLPE` | Wire type insulation if it is an IEC type (XLPE, PVC, EPR, LSZH...), otherwise XLPE |
| `PVC` | Outer sheath (fixed, `CABLE_SHEATH` in `lib/sld/revit_sld.py`) |
| `2x(...)` | More than one parallel run |

Use `SLD Cable` for anything else (single-core, armoured...). With imperial
wire sizes Revit's wire size text is shown unchanged.

## Changing the standard

Every size, text height and fixed label (`MCCB`, `ACB`, `FORM 2b`, `BUSBAR
MOUNTED FUSE @ 20A`, `R<1Ω`...) is in
[`lib/sld/style.py`](SingleLineDiagram.extension/lib/sld/style.py), in
millimetres on paper. Text notes use types named `SLD <size>mm Arial`, created
automatically and reset to these settings (size, Arial, transparent) on every
run. Text is laid out so it never needs wrapping; if you see text wrap or
touch, send a screenshot.

## Fire alarm detectors

`FireAlarm.extension` adds a **Fire Alarm** tab with a **Detectors** panel:

- **Smoke Detectors** / **Heat Detectors** – select the spaces (or click the
  button and pick them, in this model or in a linked model, or take all
  spaces on a level), and a detector is placed on the ceiling so that
  detectors are at most the spacing apart and at most half of it from the
  walls: **9 m / 4.5 m for smoke, 4.5 m / 2.25 m for heat**. Every point of
  the ceiling is then within 0.71 × spacing of a detector. The new
  detectors are selected when done, one undo removes them all, and a
  summary lists each space with its count and ceiling height.
- **FA Settings** – smoke and heat spacing, min distance from walls
  (0.5 m) and the detector family type for smoke and for heat.

![Detector layouts of the sample rooms](docs/detector-preview.png)

*Sample rooms (`tools/preview_detectors.py`): dashed lines are the grid
bays, circles show each detector's reach.*

### How the detectors are laid out

1. The grid is lined up with the space's main walls (rotated rooms get a
   rotated grid).
2. Along each direction the space is split into equal bays no longer than
   the spacing, with a detector in the middle of each bay – e.g. a 20 × 12 m
   office gets 3 × 2 smoke detectors, 6.67 m × 6 m apart, 3.33 m / 3 m from
   the walls.
3. In L, T and U shapes, around shafts and columns, the part of a bay
   inside the space gets its detector in its middle. Spaces with square
   walls are also tried as separate rectangles (the bar and the stem of a
   T); the layout with fewer detectors is used.
4. The whole ceiling is checked on a fine grid (spacing / 20) plus points
   along every wall; any point out of reach gets another detector.

Detectors stay at least 0.5 m from walls and columns, except in spaces
too narrow for it, where they go on the centreline.

### In Revit

| Item | How |
| --- | --- |
| Spaces | MEP **Spaces** or **Rooms**, in this model or in **linked models**. Select them before clicking the button, or after clicking choose: *Pick spaces in this model*, *Pick spaces or rooms in a linked model*, or *All spaces or rooms on a level* (this model or one link, one or more levels). On Revit 2023+ spaces Tab-selected inside a link before clicking are used too. The outline is the boundary at the wall finish face; shafts and columns cut out of it are kept clear. |
| Linked spaces | The outline is moved into this model with the link's position and rotation, and the detectors are placed in this model. To pick them, the link's Rooms / Spaces must be visible in the view (Visibility/Graphics → Revit Links → the link → Rooms or Spaces, *Interior* or *Reference*); *All spaces or rooms on a level* works whatever the view shows. Level-based families go on this model's level at or below the space's floor. |
| Ceiling | A ray is shot straight up from each detector point and the detector goes on the **ceiling** under the slab above – in this model or in a linked model. Where there is no ceiling under the slab it goes on the slab (floor or roof), and the summary says so; floors lower than 1.5 m (stages, raised floors) are ignored. |
| Detector family | Any family in the **Fire Alarm Devices** category. Face-based families go on the ceiling face (host or linked ceiling), ceiling-hosted families on the ceiling (only ceilings in this model can host), level-based families at ceiling height. The type is asked the first time and remembered; change it in FA Settings. |
| Detectors already there | Detectors of the same type already in the selected spaces can be replaced or kept. |

## Install

1. Install pyRevit.
2. Download this repository and unzip it somewhere permanent.
3. In Revit: **pyRevit tab → Settings → Custom Extension Directories → Add
   folder**, pick the folder that *contains* `SingleLineDiagram.extension`
   and `FireAlarm.extension`, save and reload. Both tabs (SLD, Fire Alarm)
   appear.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.

## Preview without Revit

```
python tools/preview_svg.py preview.svg
```

draws the Al Yasat sample (`tools/sample_al_yasat.py`) as an SVG you can open
in a browser. Edit the sample to try other arrangements.

```
python tools/preview_detectors.py detectors.svg [smoke spacing] [heat spacing]
```

draws the detector layout of the sample rooms (`tools/sample_rooms.py`).

## Project layout

```
SingleLineDiagram.extension/
  SLD.tab/Electrical.panel/   Generate SLD, SLD Settings buttons
  lib/sld/
    model.py       boards, ways, UPS, transformer from equipment + circuits
    layout.py      floors, placement, riser routing
    symbols.py     breaker, isolator, DB box, PFC, transformer, ACB... symbols
    geometry.py    lines, arcs and text primitives (mm)
    style.py       the drawing standard: sizes, text heights, fixed labels
    cables.py      BS / IEC cable descriptions
    revit_sld.py   reads the Revit model, draws into a drafting view
    settings.py    per-user settings
    command.py     button entry points
FireAlarm.extension/
  Fire Alarm.tab/Detectors.panel/   Smoke Detectors, Heat Detectors, FA Settings
  lib/firealarm/
    layout.py      detector points in a space outline (no Revit)
    revit_fa.py    spaces (here or in links), ceilings found by ray, placing
    report.py      summary shown after placing
    settings.py    per-user settings
    command.py     button entry points
tools/             sample models and SVG previews
tests/             pytest tests (no Revit needed)
```

## Development

```
pip install pytest
python -m pytest tests
```

Keep code in `lib/sld` and `lib/firealarm` compatible with Python 2.7 (no
f-strings, no type hints) so it runs in pyRevit's IronPython engine.
