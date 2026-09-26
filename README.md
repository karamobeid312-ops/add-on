# Single Line Diagram for Revit (pyRevit)

A [pyRevit](https://github.com/pyrevitlabs/pyRevit) extension that automatically
generates an electrical **single line diagram (SLD)** from the panels,
switchboards, transformers and circuits in a Revit model.

![Layout preview](docs/layout-preview.png)

## What it does

1. Collects all **Electrical Equipment** and **power circuits** in the model.
2. Builds the distribution tree: each piece of equipment sits under the panel
   whose circuit feeds it. Equipment with no upstream feeder becomes a source
   (top of the tree).
3. Creates a new drafting view **"Single Line Diagram"** (1:1) and draws it
   **bottom to top**: the source (e.g. main switchboard) is on the bottom row
   and each downstream level is drawn one row higher. It shows:
   - a box per equipment with its name, distribution system, mains rating and
     total connected load;
   - feeders with a breaker symbol labelled with circuit number,
     rating / poles and the cable in BS / IEC format;
   - optionally, every branch circuit above its panel.

## Cable descriptions (BS / IEC)

Cables are written as, for example:

```
4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC
```

| Part | Taken from the circuit |
| --- | --- |
| `4C` | Number of hot conductors + number of neutral conductors |
| `4mm²` | First size in Revit's *Wire Size* (needs metric wire sizes) |
| `+ 1Cx4mm²` | Number of ground conductors, and the last size in *Wire Size* (reduced earths are kept) |
| `Cu` / `Al` | Wire type material (Copper → Cu, Aluminium → Al) |
| `XLPE` | Wire type insulation if it names an IEC type (XLPE, PVC, EPR, LSZH...); otherwise XLPE |
| `PVC` | Outer sheath, fixed (`CABLE_SHEATH` in `lib/sld/revit_sld.py`) |
| `2x(...)` | Added when the circuit has more than one parallel run |

To write a cable by hand, add a text parameter named **`SLD Cable`** to
Electrical Circuits (project or shared parameter). When it has a value, it is
printed exactly as typed instead of the generated text. If the wire size is
imperial (e.g. `3-#12`), Revit's wire size text is shown unchanged.

Two buttons are added on the **SLD** tab → **Electrical** panel:

| Button | Output |
| --- | --- |
| **Generate SLD** | Equipment and feeders only (riser-style SLD) |
| **SLD With Circuits** | Also shows each branch circuit above its panel |

Each run creates a new view (`Single Line Diagram`, `Single Line Diagram 2`, ...)
so existing diagrams and any annotations on them are never overwritten.
Feed loops or equipment fed by more than one circuit are reported as warnings.

## Install

1. Install pyRevit.
2. Clone or download this repository.
3. In Revit: **pyRevit tab → Settings → Custom Extension Directories → Add
   folder**. Pick the folder that *contains* `SingleLineDiagram.extension`
   (the repository root), save, and reload pyRevit.

Works with pyRevit's default IronPython 2.7 engine and the CPython 3 engine.

## Model requirements

- Panels/switchboards placed as **Electrical Equipment** family instances.
- Downstream equipment connected to an upstream panel through a power circuit
  (select the equipment → *Power* circuit → *Select Panel*).
- The panel name is read from the **Panel Name** parameter (falls back to the
  family instance name).

## Project layout

```
SingleLineDiagram.extension/
  SLD.tab/Electrical.panel/     ribbon buttons (pyRevit bundles)
  lib/sld/
    model.py       Revit-independent data model + tree builder
    layout.py      Revit-independent layout -> lines & text (paper inches)
    cables.py      BS / IEC cable descriptions
    revit_sld.py   Reads the Revit model and draws into a drafting view
    command.py     Shared button entry point (pyRevit UI)
tests/             pytest tests for model.py, layout.py and cables.py
```

## Development

The diagram logic has no Revit dependency and is covered by tests:

```
pip install pytest
python -m pytest tests
```

Keep code in `lib/sld` compatible with Python 2.7 (no f-strings, no type
hints) so it runs in pyRevit's IronPython engine.
