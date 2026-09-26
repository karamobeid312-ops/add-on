# LV Schematic Diagram for Revit (pyRevit)

A [pyRevit](https://github.com/pyrevitlabs/pyRevit) extension that automatically
draws the **low voltage system schematic diagram** of a Revit model in the
office standard format (as drawing 2427 0EE 321): boards on their floors,
every outgoing way, UPS, main boards with transformer and supply.

![Preview of the Al Yasat sample](docs/layout-preview.png)

*Preview of the built-in Al Yasat sample (`tools/preview_svg.py`), no Revit needed.*

## What gets drawn

| Item | How |
| --- | --- |
| **Floors** | One band per Revit level, dashed floor line and label (`ROOF FLOOR`, `GROUND FLOOR`...). Main boards go in the `SUBSTATION` band at the bottom. The diagram reads bottom to top. |
| **Boards** (MDB, SMDB, USMDB...) | Box with busbar, every outgoing way numbered (1, 2..., R9/Y9/B9 for single-phase) with an `MCCB` breaker, incomer MCCB under the busbar, and `FORM 2b, 18 WAYS` / `LOCATION: ...` / `@ FLOOR` / board name. |
| **Main boards** | `FORM4-TYPE6`, `LOCATION:LV ROOM`, CT with 3 ammeters, indicator lamps, withdrawable ACB, busbar mounted fuse, SPD to earth `R<1Ω`, incoming cable, transformer, `MV CABLE FROM TAQA`, `FROM TAQA`. |
| **Final DBs** (LDB, PDB, DB-...) | Tall box with the name, at the end of the way. A DB on a higher floor than its board is drawn on its own floor, fed by a riser (like UDB-FF-01 from USMDB-GF-M). |
| **Equipment** (AHU, VRF, pumps, EV...) | Local isolator with the load name. |
| **Spare ways** | `SPARE`. |
| **PFC** | Capacitor bank symbol, `POWER FACTOR CORRECTION`. |
| **UPS** | Box across the ways that feed it; its output rises to the UPS board. |
| **Feeders between boards** | Risers straight up from the way, jogging around any board in the way and lining up under the fed board's incomer. |
| **Ratings** (optional) | Breaker rating and BS/IEC cable along each way, e.g. `63A TP` / `4Cx16mm² Cu/XLPE/PVC` / `+ 1Cx16mm² Cu/XLPE/PVC`. |

Buttons on the **SLD** tab → **Electrical** panel:

- **Generate SLD** – creates a new drafting view `LV Schematic Diagram`
  (`LV Schematic Diagram 2`, ... on later runs; earlier diagrams are never
  overwritten). The view is 1:1, so sizes match the printed sheet; place it
  on your A1 title block sheet.
- **SLD Settings** – utility name (`TAQA`), bottom band label (`SUBSTATION`),
  ratings on/off, and way numbering (ways from slots, or Revit circuit numbers).

## How the model is read

| Drawing | Revit |
| --- | --- |
| Board / DB / main board | **Electrical Equipment**. Equipment that feeds other equipment, or whose name looks like a board (`MDB`, `SMDB`, `USMDB`, `MSB`...), is a board. Equipment with no supply is a main board. Everything else is a final DB. |
| Transformer | Electrical equipment whose family part type is *Transformer* (or family name contains `TRANSFORMER`) feeding a main board. |
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
automatically.

## Install

1. Install pyRevit.
2. Download this repository and unzip it somewhere permanent.
3. In Revit: **pyRevit tab → Settings → Custom Extension Directories → Add
   folder**, pick the folder that *contains* `SingleLineDiagram.extension`,
   save and reload.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.

## Preview without Revit

```
python tools/preview_svg.py preview.svg
```

draws the Al Yasat sample (`tools/sample_al_yasat.py`) as an SVG you can open
in a browser. Edit the sample to try other arrangements.

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
tools/             sample model and SVG preview
tests/             pytest tests (no Revit needed)
```

## Development

```
pip install pytest
python -m pytest tests
```

Keep code in `lib/sld` compatible with Python 2.7 (no f-strings, no type
hints) so it runs in pyRevit's IronPython engine.
