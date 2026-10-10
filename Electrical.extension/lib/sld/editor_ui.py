# -*- coding: utf-8 -*-
"""The LV Schematic Editor window (WPF).

Works with pyRevit's IronPython 2.7 and CPython 3 engines: the XAML is
loaded with XamlReader (pyrevit.forms.WPFWindow is IronPython only), events
are wired here, and the grid shows a System.Data.DataTable of text columns
(WPF cannot bind to Python objects under CPython). The data and rules live
in sld/editor.py; this module only shows them.
"""
from __future__ import division

import os

from sld import editor as ed

XAML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor.xaml")
TITLE = "LV Schematic Editor"
NUMBERING = (("slots", "Ways numbered in order (1, 2, R9, Y9, B9)"),
             ("revit", "Revit circuit numbers"))

# grid columns: (data column, header, width, kind) kind: ro / combo / text
COLUMNS = (
    ("label", "Way", 45, "ro"), ("feeds", "Feeds", 170, "ro"),
    ("at", "AT", 60, "combo"), ("af", "AF", 60, "combo"), ("device", "Type", 70, "combo"),
    ("poles", "Poles", 45, "ro"), ("runs", "Runs", 45, "combo"),
    ("cores", "Cores", 50, "combo"), ("size", u"Size mm²", 70, "combo"),
    ("material", "Cu/Al", 55, "combo"), ("insulation", "Insulation", 75, "combo"),
    ("armour", "Armour", 65, "combo"), ("earth", u"Earth mm²", 75, "combo"),
    ("length", "Length m", 70, "text"), ("vd", "V.D %", 60, "vd"),
)
HIDDEN = ("key",)
FLAGS = ("vd_over", "locked")
BOARD_CONTROLS = (("IncomerAT", "incomer_at"), ("IncomerAF", "incomer_af"),
                  ("IncomerDevice", "incomer_device"), ("FaultLevel", "fault_level"),
                  ("WaysCount", "ways"), ("SpareCount", "spares"), ("SpareAT", "spare_at"),
                  ("SpareAF", "spare_af"), ("SpareDevice", "spare_device"))
NAMES = ("BoardsTree", "BoardTitle", "WaysGrid", "PreviewText", "WarningsText", "SaveButton",
         "GenerateButton", "CloseButton", "AddSpare", "RemoveSpare", "SetUtility",
         "SetSubstation", "SetShowRatings", "SetNumbering") + tuple(n for n, _ in BOARD_CONTROLS)


def column_xaml(field, header, width, kind):
    """XAML of one grid column; combos are editable (free text allowed)."""
    header = header.replace(u"²", "&#178;")
    if kind in ("ro", "vd", "text"):
        extra = ' IsReadOnly="True"' if kind != "text" else ""
        if kind == "vd":
            extra += ' CellStyle="{StaticResource VdCell}"'
        return ('<DataGridTextColumn Header="%s" Width="%d" Binding="{Binding %s}"%s/>'
                % (header, width, field, extra))
    return (
        '<DataGridTemplateColumn Header="%(h)s" Width="%(w)d">'
        '<DataGridTemplateColumn.CellTemplate><DataTemplate>'
        '<TextBlock Text="{Binding %(f)s}" Padding="2,0"/>'
        '</DataTemplate></DataGridTemplateColumn.CellTemplate>'
        '<DataGridTemplateColumn.CellEditingTemplate><DataTemplate>'
        '<ComboBox Style="{StaticResource EditCombo}" ItemsSource="{DynamicResource ch_%(f)s}" '
        'Text="{Binding %(f)s, UpdateSourceTrigger=PropertyChanged}"/>'
        '</DataTemplate></DataGridTemplateColumn.CellEditingTemplate>'
        '</DataGridTemplateColumn>' % {"h": header, "w": width, "f": field})


def window_xaml():
    with open(XAML_FILE, "rb") as f:
        text = f.read().decode("utf-8")
    columns = "\n".join(column_xaml(*c) for c in COLUMNS)
    return text.replace("\nCOLUMNS\n", "\n" + columns + "\n", 1)


def row_values(way):
    """{data column: text} for a grid row."""
    values = {"key": way.key, "label": way.label, "feeds": way.feeds, "poles": way.poles,
              "vd": way.vd}
    for field in ed.FIELDS:
        values[field] = way.values.get(field, "")
    return values


def row_flags(way):
    return {"vd_over": bool(way.vd_over),
            "locked": not any(way.editable(f) for f in ed.FIELDS)}


def warnings_text(warnings, limit=2):
    if not warnings:
        return u""
    text = u"⚠ " + u"   ⚠ ".join(warnings[:limit])
    if len(warnings) > limit:
        text += u"   (+%d more)" % (len(warnings) - limit)
    return text


def spare_count(text, step):
    try:
        n = int(float(text or 0))
    except ValueError:
        n = 0
    return str(max(n + step, 0))


# ---------------------------------------------------------------- window

class EditorWindow(object):
    """Plain controller around the XamlReader window (no .NET subclass, so
    nothing to register under CPython)."""

    def __init__(self, editor, settings_values, on_save):
        import clr
        for name in ("PresentationFramework", "PresentationCore", "WindowsBase",
                     "System.Xaml", "System.Data", "System.Data.Common"):
            try:
                clr.AddReference(name)
            except Exception:
                pass
        from System.Windows.Markup import XamlReader
        self.editor = editor
        self.settings = dict(settings_values)
        self.on_save = on_save
        self.action = "close"
        self.current = None
        self.table = None
        self.rows = {}
        self._busy = False
        self.win = XamlReader.Parse(window_xaml())
        for name in NAMES:
            setattr(self, name, self.win.FindName(name))
        self._set_owner()
        self._fill_choices()
        self._fill_settings()
        self._fill_tree()
        self._wire()
        self._show_warnings()

    # ------------------------------------------------------------ setup

    def _set_owner(self):
        try:
            from pyrevit import HOST_APP
            from System.Windows.Interop import WindowInteropHelper
            WindowInteropHelper(self.win).Owner = HOST_APP.proc_window
        except Exception:
            pass

    def _strings(self, values):
        from System import String
        from System.Collections.Generic import List
        out = List[String]()
        for v in values:
            out.Add(u"%s" % v)
        return out

    def _fill_choices(self):
        for key, values in ed.CHOICES.items():
            self.win.Resources["ch_%s" % key] = self._strings(values)

    def _fill_settings(self):
        s = self.settings
        self.SetUtility.Text = s.get("utility", "")
        self.SetSubstation.Text = s.get("substation_label", "")
        self.SetShowRatings.IsChecked = bool(s.get("show_ratings", True))
        for _, label in NUMBERING:
            self.SetNumbering.Items.Add(label)
        keys = [k for k, _ in NUMBERING]
        self.SetNumbering.SelectedIndex = keys.index(s.get("numbering", "slots")) \
            if s.get("numbering") in keys else 0

    def _fill_tree(self):
        from System.Windows.Controls import TreeViewItem

        def add(items, board):
            item = TreeViewItem()
            item.Header = board.name
            item.Tag = board.id
            item.IsExpanded = True
            items.Add(item)
            for child in board.children:
                add(item.Items, child)
            return item

        first = None
        for root in self.editor.roots:
            item = add(self.BoardsTree.Items, root)
            first = first or item
        if first is not None:
            first.IsSelected = True
            self._show_board(first.Tag)

    def _wire(self):
        self.BoardsTree.SelectedItemChanged += self.on_board
        self.WaysGrid.BeginningEdit += self.on_beginning_edit
        self.WaysGrid.CellEditEnding += self.on_cell_edit_ending
        self.WaysGrid.CurrentCellChanged += self.on_current_cell
        self.SaveButton.Click += self.on_save_click
        self.GenerateButton.Click += self.on_generate
        self.CloseButton.Click += self.on_close_click
        self.AddSpare.Click += self.on_add_spare
        self.RemoveSpare.Click += self.on_remove_spare
        self.win.Closing += self.on_closing
        for name, _ in BOARD_CONTROLS:
            control = getattr(self, name)
            control.LostKeyboardFocus += self.on_board_field
            control.KeyDown += self.on_board_key
            if hasattr(control, "DropDownClosed"):
                control.DropDownClosed += self.on_board_field

    def show(self):
        self.win.ShowDialog()
        return self.action, self._read_settings()

    # ------------------------------------------------------------ helpers

    def _alert(self, text, ask=False):
        from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
        if not ask:
            MessageBox.Show(self.win, text, TITLE)
            return None
        result = MessageBox.Show(self.win, text, TITLE, MessageBoxButton.YesNoCancel)
        return {MessageBoxResult.Yes: "yes", MessageBoxResult.No: "no"}.get(result, "cancel")

    def _safe(self, fn, *args):
        try:
            return fn(*args)
        except Exception as error:
            import traceback
            self._alert(u"%s\n\n%s" % (error, traceback.format_exc()))

    def _commit(self):
        from System.Windows.Controls import DataGridEditingUnit
        self._busy = True
        try:
            self.WaysGrid.CommitEdit(DataGridEditingUnit.Row, True)
        finally:
            self._busy = False

    def _read_settings(self):
        s = dict(self.settings)
        s["utility"] = (self.SetUtility.Text or "").strip().upper() or s.get("utility", "")
        s["substation_label"] = ((self.SetSubstation.Text or "").strip().upper() or
                                 s.get("substation_label", ""))
        s["show_ratings"] = bool(self.SetShowRatings.IsChecked)
        index = self.SetNumbering.SelectedIndex
        if 0 <= index < len(NUMBERING):
            s["numbering"] = NUMBERING[index][0]
        return s

    # ------------------------------------------------------------ board

    def _show_board(self, board_id):
        from System import Boolean, String
        from System.Data import DataTable
        board = self.editor.board(board_id)
        self.current = board_id
        self.BoardTitle.Text = board.name
        self._busy = True
        try:
            for name, field in BOARD_CONTROLS:
                getattr(self, name).Text = board.values.get(field, "")
        finally:
            self._busy = False
        table = DataTable("Ways")
        for name in HIDDEN + tuple(c[0] for c in COLUMNS):
            table.Columns.Add(name, String).DefaultValue = u""
        for name in FLAGS:
            table.Columns.Add(name, Boolean).DefaultValue = False
        self.rows = {}
        for way in self.editor.ways(board_id):
            row = table.NewRow()
            self._write_row(row, way)
            table.Rows.Add(row)
            self.rows[way.key] = row
        table.AcceptChanges()
        self.table = table
        self.WaysGrid.ItemsSource = table.DefaultView
        self.PreviewText.Text = u""
        self._show_warnings()

    def _write_row(self, row, way):
        for name, value in row_values(way).items():
            row[name] = u"%s" % (value or u"")
        for name, value in row_flags(way).items():
            row[name] = value

    def _refresh(self, keys):
        for key in keys:
            row = self.rows.get(key)
            if row is not None:
                self._write_row(row, self.editor.way(key))
        self._show_warnings()

    def _show_warnings(self):
        warnings = self.editor.warnings()
        self.WarningsText.Text = warnings_text(warnings)
        self.WarningsText.ToolTip = u"\n".join(warnings) if warnings else None

    def _row_key(self, item):
        try:
            return u"%s" % item.Row["key"]
        except Exception:
            return None

    # ------------------------------------------------------------ events

    def on_board(self, sender, args):
        item = args.NewValue
        if item is not None:
            self._commit()
            self._safe(self._show_board, item.Tag)

    def on_beginning_edit(self, sender, args):
        key = self._row_key(args.Row.Item)
        index = self.WaysGrid.Columns.IndexOf(args.Column)
        field = COLUMNS[index][0] if 0 <= index < len(COLUMNS) else ""
        if key is None or not self.editor.way(key).editable(field):
            args.Cancel = True

    def on_cell_edit_ending(self, sender, args):
        from System import Action
        from System.Windows.Controls import DataGridEditAction
        from System.Windows.Threading import DispatcherPriority
        if self._busy or args.EditAction != DataGridEditAction.Commit:
            return
        key = self._row_key(args.Row.Item)
        index = self.WaysGrid.Columns.IndexOf(args.Column)
        if key is None or not 0 <= index < len(COLUMNS):
            return
        field = COLUMNS[index][0]
        # the new text reaches the row after this event: read it afterwards
        self.win.Dispatcher.BeginInvoke(DispatcherPriority.Background,
                                        Action(lambda: self._safe(self._after_edit, key, field)))

    def _after_edit(self, key, field):
        self._commit()
        row = self.rows.get(key)
        if row is None:
            return
        value = row[field]
        text = u"" if value is None or u"%s" % value == u"" else u"%s" % value
        changed = self.editor.set_way(key, field, text)
        self._refresh(changed or [key])
        self._preview(key)

    def on_current_cell(self, sender, args):
        cell = self.WaysGrid.CurrentCell
        key = self._row_key(cell.Item) if cell.Item is not None else None
        if key:
            self._safe(self._preview, key)

    def _preview(self, key):
        way = self.editor.way(key)
        cable, breaker = self.editor.preview(key)
        text = u"Way %s prints as: %s" % (way.label, cable or u"(no cable)")
        if breaker:
            text += u"     %s" % breaker
        if way.vd_tip:
            text += u"\n%s" % way.vd_tip.replace(u"\n", u"   ")
        self.PreviewText.Text = text

    def on_board_key(self, sender, args):
        from System.Windows.Input import Key
        if args.Key == Key.Enter:
            self.on_board_field(sender, args)

    def on_board_field(self, sender, args):
        if self._busy or self.current is None:
            return
        field = next(f for n, f in BOARD_CONTROLS if getattr(self, n) is sender or
                     getattr(self, n).Equals(sender))
        self._safe(self._set_board, field, sender.Text)

    def _set_board(self, field, text):
        board = self.editor.board(self.current)
        if (board.values.get(field, "") or "") == (text or "").strip().upper() or \
                (board.values.get(field, "") or "") == (text or "").strip():
            return
        if self.editor.set_board(self.current, field, text):
            self._commit()
            self._show_board(self.current)
        else:
            self._show_warnings()

    def _step_spares(self, step):
        self._commit()
        board = self.editor.board(self.current)
        self.editor.set_board(self.current, "spares", spare_count(board.values["spares"], step))
        self._show_board(self.current)

    def on_add_spare(self, sender, args):
        if self.current is not None:
            self._safe(self._step_spares, 1)

    def on_remove_spare(self, sender, args):
        if self.current is not None:
            self._safe(self._step_spares, -1)

    def on_save_click(self, sender, args):
        self._commit()
        self._safe(self._save)

    def _save(self):
        message = self.on_save(self.editor)
        self._show_board(self.current)
        self._alert(message)

    def on_generate(self, sender, args):
        self._commit()
        self.action = "generate"
        self.win.Close()

    def on_close_click(self, sender, args):
        self.win.Close()

    def on_closing(self, sender, args):
        self._commit()
        if self.action == "generate" or not self.editor.dirty():
            return
        answer = self._alert("Save your changes to Revit before closing?", ask=True)
        if answer == "cancel":
            args.Cancel = True
        elif answer == "yes":
            self._safe(lambda: self.on_save(self.editor))


def show_editor(editor, settings_values, on_save):
    """Show the window (modal). on_save(editor) writes to Revit and returns
    a message. Returns ('generate' or 'close', settings values)."""
    return EditorWindow(editor, settings_values, on_save).show()
