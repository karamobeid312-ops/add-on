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
3. Creates a new drafting view **"Single Line Diagram"** (1:1) and draws:
   - a box per equipment with its name, distribution system, mains rating and
     total connected load;
   - feeders with a breaker symbol labelled with circuit number,
     rating / poles and wire size;
   - optionally, every branch circuit under its panel.

Two buttons are added on the **SLD** tab → **Electrical** panel:

| Button | Output |
| --- | --- |
| **Generate SLD** | Equipment and feeders only (riser-style SLD) |
| **SLD With Circuits** | Also lists each branch circuit under its panel |

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
    revit_sld.py   Reads the Revit model and draws into a drafting view
    command.py     Shared button entry point (pyRevit UI)
tests/             pytest tests for model.py and layout.py
```

## Development

The diagram logic has no Revit dependency and is covered by tests:

```
pip install pytest
python -m pytest tests
```

Keep code in `lib/sld` compatible with Python 2.7 (no f-strings, no type
hints) so it runs in pyRevit's IronPython engine.
