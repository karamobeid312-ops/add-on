# -*- coding: utf-8 -*-
import re
import xml.etree.ElementTree as ET

from sld import editor as ed
from sld import editor_ui as ui
from test_editor import small

X = "{http://schemas.microsoft.com/winfx/2006/xaml}"


def test_window_xaml_is_valid_with_every_named_control():
    text = ui.window_xaml()
    root = ET.fromstring(text.encode("utf-8"))
    names = set(el.get(X + "Name") for el in root.iter() if el.get(X + "Name"))
    assert set(ui.NAMES) <= names
    assert root.get(X + "Class") is None
    events = ("Click", "SelectionChanged", "Loaded", "KeyDown", "LostFocus", "Closing")
    assert not [el.tag for el in root.iter() for e in events if el.get(e) is not None]
    assert text.count("DataGridTemplateColumn Header") == sum(
        1 for c in ui.COLUMNS if c[3] == "combo")


def test_every_combo_column_has_choices():
    for field, _, _, kind in ui.COLUMNS:
        if kind == "combo":
            assert field in ed.CHOICES
    for _, field in ui.BOARD_CONTROLS:
        assert field in ed.BOARD_FIELDS
    resources = set(re.findall(r"ch_(\w+)", open(ui.XAML_FILE).read()))
    # fed_by, typical: board names; riser_names: the bus bar risers
    assert resources <= set(ed.CHOICES) | {"fed_by", "typical", "riser_names"}


def test_row_values_and_flags():
    editor = small(vd=False)
    way = editor.ways("SMDB-1")[0]
    values = ui.row_values(way)
    assert values["feeds"] == "LIGHTS" and values["size"] == "6" and values["at"] == "32"
    assert set(c[0] for c in ui.COLUMNS) <= set(values)
    assert ui.row_flags(way) == {"vd_over": False, "locked": False, "sized": False}
    spare = [w for w in editor.ways("SMDB-1") if w.added][0]
    assert ui.row_flags(spare)["locked"] is True


def test_small_helpers():
    assert ui.spare_count("3", 1) == "4" and ui.spare_count("0", -1) == "0"
    assert ui.spare_count("", 1) == "1"
    assert ui.warnings_text([]) == ""
    assert "(+1 more)" in ui.warnings_text(["a", "b", "c"])


def test_themed_window_resolves_every_resource():
    text = ui.themed_xaml()
    assert "__ACCENT" not in text and "<!--THEME-->" not in text
    root = ET.fromstring(text.encode("utf-8"))
    names = set(el.get(X + "Name") for el in root.iter() if el.get(X + "Name"))
    assert set(ui.NAMES) <= names
    keys = set(el.get(X + "Key") for el in root.iter() if el.get(X + "Key"))
    for key in re.findall(r"\{StaticResource ([^}{]+)\}", text):
        assert key in keys, key
    for key in re.findall(r"\{DynamicResource ([^}]+)\}", text):
        assert key in keys or key.startswith("ch_"), key
    # the theme's own brushes for the status chips and dots
    assert {"OkBrush", "WarnBrush", "BadBrush", "NoneBrush", "AccentBrush"} <= keys


def test_vd_grid_columns():
    from sld import studio
    text = ui.window_xaml()
    assert "\nVDCOLUMNS\n" not in text and "\nCOLUMNS\n" not in text
    assert text.count('CellTemplate="{StaticResource StatusChip}"') == 1
    assert text.count('CellTemplate="{StaticResource VdChip}"') == 1
    assert all(('Binding="{Binding %s}"' % f) in text
               for f, _, _ in studio.VD_COLUMNS if f != "status")


def test_way_state_and_overall_state():
    editor = small()
    lights = editor.ways("SMDB-1")[0]
    assert ui.row_values(lights)["vd_state"] == "ok"
    editor.set_way(lights.key, "length", "900")
    assert lights.vd_over and ui.row_values(lights)["vd_state"] == "bad"
    assert ui.overall_state(editor) == "bad"
