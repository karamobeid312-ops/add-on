# LV Schematic Diagram for Revit (pyRevit)

A [pyRevit](https://github.com/pyrevitlabs/pyRevit) extension that automatically
draws the **low voltage system schematic diagram** of a Revit model in the
office standard format (as drawing 2427 0EE 321): boards on their floors,
every outgoing way, UPS, main boards with transformer and supply.

![Preview of the Al Yasat sample](docs/layout-preview.png)

*Preview of the built-in Al Yasat sample (`tools/preview_svg.py`), no Revit needed.*

The repository also holds a **Fire Alarm** extension that places smoke and
heat detectors in the selected spaces, see [Fire alarm detectors](#fire-alarm-detectors),
and a **Voltage Drop** extension that calculates the voltage drop of every
cable and saves the office voltage drop sheet, see [Voltage drop](#voltage-drop).

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
  button and pick them), and a detector is placed on the ceiling so that
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
| Spaces | MEP **Spaces** (or Rooms) in the model, pre-selected or picked. The outline is the space boundary at the wall finish face; shafts and columns cut out of it are kept clear. |
| Ceiling | A ray is shot straight up from each detector point and the detector goes on the **ceiling** under the slab above – in this model or in a linked model. Where there is no ceiling under the slab it goes on the slab (floor or roof), and the summary says so; floors lower than 1.5 m (stages, raised floors) are ignored. |
| Detector family | Any family in the **Fire Alarm Devices** category. Face-based families go on the ceiling face (host or linked ceiling), ceiling-hosted families on the ceiling (only ceilings in this model can host), level-based families at ceiling height. The type is asked the first time and remembered; change it in FA Settings. |
| Detectors already there | Detectors of the same type already in the selected spaces can be replaced or kept. |

## Voltage drop

`VoltageDrop.extension` adds a **Voltage Drop** tab with a **Calculation** panel:

- **Calculate VD** – calculates the incoming cable of every panel, from the
  transformer down, and every final circuit with a length. Writes
  `VD Percent` and `VD Total Percent` on each panel and lists the results
  in the output window: first a **To fix** list of what is missing in the
  model (lengths, cable sizes, loads, breaker ratings), then every cable
  that fails with the breaker or cable that would pass (e.g. `V.D 5.52% >
  4%; use 4Cx25mm²`). Click an element id to select the panel.
- **VD Report** – saves the calculation as an Excel file in the office
  voltage drop sheet format (S.N, FROM, TO, DISTANCE ... CUMULATIVE V.D (%),
  MAX V.D %) with a REMARKS column, and opens it. The cells hold formulas,
  so a length or load changed in Excel updates the voltage drop.
- **VD Settings** – voltages, default power factor, demand (MDL) or
  connected (TCL) load, limits, default cable and installation, derating
  values and the report title block (company, revision, issue).

The SLD is not changed.

### Typing the lengths

Everything about a panel's incoming cable is typed on the **panel**. The
first time you click **Calculate VD** it offers to add these instance
parameters, and a **Voltage Drop Panels** schedule (panel name, supply
from, MCB rating, mains, demand load and the VD parameters) where you type
every length in one place:

| Parameter | Type | On | What you type |
| --- | --- | --- | --- |
| `VD Length` | Text | panels, circuits, electrical and lighting fixtures, mechanical equipment | length of the incoming cable in metres: `175`, `175 m` (also `mm`, `ft`) |
| `VD Installation` | Text | panels, circuits | `Cable Tray`, `Duct Bank` or `Ground`; empty = VD Settings |
| `VD Cable` | Text | panels, circuits | when Revit's wire size is not the cable: `4Cx16`, `4x4Cx300`, `11x1Cx630 XLPE/SWA/PVC` |
| `VD Load kW` | Text | panels, circuits | only to override the load: the maximum demand in kW |
| `VD Percent` | Number | panels, circuits | result: voltage drop of the incoming cable (%) |
| `VD Total Percent` | Number | panels, circuits | result: cumulative voltage drop at the panel (%) |

Every panel fed from another panel or a transformer gets a row (a missing
length is reported). A main board with no supply circuit gets a row for the
cable from the transformer when `VD Length` (and `VD Cable`, e.g.
`11x1Cx630`) is typed on it.

Final circuits (AHU, pumps, lights...) are calculated when `VD Length` is
typed on their equipment or fixtures; with several on one circuit the
farthest one counts. A value typed on a circuit is still used when the
panel or fixture has none.

### What is read from Revit

For a panel's incoming cable:

| Sheet column | Revit |
| --- | --- |
| FROM / TO | Supply From (the board feeding it) / Panel Name |
| PHASE, VOLTAGE | the panel's distribution system (line to line voltage) |
| TCL (kW) | Total Connected x PF |
| MDL (kW) | `VD Load kW`, or Total Estimated Demand x PF (with MDL in VD Settings), else TCL |
| PF | the feeding circuit's power factor, else VD Settings |
| Breaker rating | MCB Rating, else Mains, else the feeding circuit's Rating |
| Runs, cores, CSA | `VD Cable`, else `SLD Incoming Cable`, else the feeding circuit's wire size (Revit keeps it only there) |
| Insulation | from `VD Cable`, else VD Settings (XLPE/SWA/PVC) |

A final circuit is read from the circuit (its panel, load, rating, poles,
voltage, wire size), with the length from its loads.

The cable tables are metric: with imperial wire sizes (`3-#4/0, 1-#4/0`)
use a metric wire size table in Revit or type each cable in `VD Cable`.
Set the **MCB Rating** (or Mains) of every panel: without it the breaker
is the feeding circuit's Rating, which Revit sets to 20 A for new circuits.

### How it is calculated

As the office sheet:

```
I (A)       = MDL kVA x 1000 / (√3 x 400 V)          single phase: / 230 V
breaker     In >= 1.1 x I
cable       Iz = rating x runs x Cb x Ca x Cr x Cg >= In
V.D (V)     = mV/A/m / runs x L (m) x I (A) / 1000
V.D (%)     = V.D / V x 100
cumulative  = V.D (%) + cumulative V.D (%) of the cable feeding the FROM board
limit       2.5 % transformer to main board, 4 % to the final load
```

Ratings, mV/A/m and the derating factors Ca (temperature), Cb (depth) and
Cr (soil thermal resistivity) are the office sheet's DUCAB XLPE tables, in
[`lib/vdrop/tables.py`](VoltageDrop.extension/lib/vdrop/tables.py). Where
the tool differs from the sheet:

- √3 instead of 1.73 (0.12 % lower).
- Single phase cables use 230 V and 2/√3 x the three phase mV/A/m (the
  sheet has no single phase rows).
- The cumulative total starts again after a transformer or a UPS.
- Cr uses the size bands of the table headings (multicore up to 16 / 150
  mm², single core up to 150 / 300 mm²); the sheet's formula uses 16 / 240
  for both. Same result with resistivity 0, as in the sheet.
- Cb and Cr are picked by single core / multicore, the sheet picks them by
  the number of phases.
- Only XLPE cables: the sheet's `ref_PVC` tab is a copy of the XLPE data.

## Install

1. Install pyRevit.
2. Download this repository and unzip it somewhere permanent.
3. In Revit: **pyRevit tab → Settings → Custom Extension Directories → Add
   folder**, pick the folder that *contains* `SingleLineDiagram.extension`,
   `FireAlarm.extension` and `VoltageDrop.extension`, save and reload. The
   tabs (SLD, Fire Alarm, Voltage Drop) appear.

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

```
python tools/preview_vd_report.py report.xlsx
```

saves the voltage drop report of the sample cables (`tools/sample_vd.py`,
the rows of an office voltage drop sheet).

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
    revit_fa.py    spaces, ceilings found by ray, placing the family
    report.py      summary shown after placing
    settings.py    per-user settings
    command.py     button entry points
VoltageDrop.extension/
  Voltage Drop.tab/Calculation.panel/   Calculate VD, VD Report, VD Settings
  lib/vdrop/
    calc.py        voltage drop, cable and breaker checks, suggestions (no Revit)
    tables.py      cable ratings, mV/A/m, derating factors of the office sheet
    parse.py       reading the typed lengths, cables, installations
    report.py      the report in the office sheet layout, results summary
    xlsx.py        small .xlsx writer (standard library only)
    revit_vd.py    panels and circuits to rows, results to parameters, setup
    settings.py    per-user settings
    command.py     button entry points
tools/             sample models, SVG and report previews
tests/             pytest tests (no Revit needed)
```

## Development

```
pip install pytest
python -m pytest tests
```

Keep code in `lib/sld`, `lib/firealarm` and `lib/vdrop` compatible with Python 2.7 (no
f-strings, no type hints) so it runs in pyRevit's IronPython engine.
