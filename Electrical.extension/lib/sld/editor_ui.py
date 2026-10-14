# -*- coding: utf-8 -*-
"""The Power Studio window (WPF): boards and ways, the voltage drop of
every cable, and the settings, in the Electrical tab's shared look (ui).

Works with pyRevit's IronPython 2.7 and CPython 3 engines: the XAML is
loaded with XamlReader (pyrevit.forms.WPFWindow is IronPython only), events
are wired here, and the grids show System.Data.DataTables of text columns
(WPF cannot bind to Python objects under CPython). The data and rules live
in sld/editor.py and sld/studio.py; this module only shows them.
"""
from __future__ import division

import os

import elecui as ui
from sld import editor as ed
from sld import studio

XAML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor.xaml")
TITLE = "Power Studio"
ACCENT = "power"
NUMBERING = studio.NUMBERING

# ways grid: (data column, header, width, kind) kind: ro / combo / text / vd
COLUMNS = (
    ("label", "Way", 45, "ro"), ("feeds", "Feeds", 170, "ro"),
    ("at", "AT", 60, "combo"), ("af", "AF", 60, "combo"), ("device", "Type", 70, "combo"),
    ("poles", "Poles", 45, "ro"), ("phase", "Phase", 50, "ro"),
    ("runs", "Runs", 45, "combo"),
    ("cores", "Cores", 50, "combo"), ("size", u"Size mm²", 70, "combo"),
    ("material", "Cu/Al", 55, "combo"), ("insulation", "Insulation", 75, "combo"),
    ("armour", "Armour", 65, "combo"), ("earth", u"Earth mm²", 75, "combo"),
    ("length", "Length m", 70, "text"), ("vd", "V.D %", 90, "vd"),
)
HIDDEN = ("key", "vd_state")
FLAGS = ("vd_over", "locked", "sized")
BOARD_CONTROLS = (("IncomerAT", "incomer_at"), ("IncomerAF", "incomer_af"),
                  ("IncomerDevice", "incomer_device"), ("FaultLevel", "fault_level"),
                  ("WaysCount", "ways"), ("SpareCount", "spares"), ("SpareAT", "spare_at"),
                  ("SpareAF", "spare_af"), ("SpareDevice", "spare_device"),
                  ("SpaceCount", "spaces"),
                  ("FedBy", "fed_by"), ("TxVd", "tx_vd"))
NAMES = ("Steps", "BoardsTab", "VdTab", "SettingsTab", "ModelText", "StatusDot",
         "BoardsTree", "BoardTitle", "BoardChip", "BoardChipText", "BoardWays",
         "KpiConnected", "KpiDemand", "KpiIncomer", "KpiVd", "KpiBalance", "KpiBalanceSub",
         "WaysGrid", "PreviewText", "WarningsText", "SaveButton", "AutoSizeButton",
         "ReportButton", "GenerateButton", "CloseButton", "AddSpare", "RemoveSpare",
         "AddSpace", "RemoveSpace",
         "VdTabText", "VdDot", "VdCables", "VdOk", "VdFailed", "VdIncomplete", "VdWorst",
         "VdWorstWhere", "VdFixes", "VdProblemsOnly", "VdSearch", "VdGrid",
         "SldSettingsPanel", "VdSettingsPanel", "ApplySettings", "SettingsNote") + \
    tuple(n for n, _ in BOARD_CONTROLS)
STATE_TEXT = {studio.OK: u"OK", studio.WARN: u"Check", studio.BAD: u"Problem"}


def column_xaml(field, header, width, kind):
    """XAML of one ways grid column; combos are editable (free text allowed)."""
    header = header.replace(u"²", "&#178;")
    if kind == "vd":
        return ('<DataGridTemplateColumn IsReadOnly="True" Header="%s" Width="%d" '
                'CellTemplate="{StaticResource VdChip}"/>' % (header, width))
    if kind in ("ro", "text"):
        extra = ' IsReadOnly="True"' if kind == "ro" else ""
        return ('<DataGridTextColumn Header="%s" Width="%d" Binding="{Binding %s}"%s/>'
                % (header, width, field, extra))
    return (
        '<DataGridTemplateColumn Header="%(h)s" Width="%(w)d">'
        '<DataGridTemplateColumn.CellTemplate><DataTemplate>'
        '<TextBlock Text="{Binding %(f)s}" Padding="2,0" VerticalAlignment="Center"/>'
        '</DataTemplate></DataGridTemplateColumn.CellTemplate>'
        '<DataGridTemplateColumn.CellEditingTemplate><DataTemplate>'
        '<ComboBox Style="{StaticResource EditCombo}" ItemsSource="{DynamicResource ch_%(f)s}" '
        'Text="{Binding %(f)s, UpdateSourceTrigger=PropertyChanged}"/>'
        '</DataTemplate></DataGridTemplateColumn.CellEditingTemplate>'
        '</DataGridTemplateColumn>' % {"h": header, "w": width, "f": field})


def vd_column_xaml(field, header, width):
    """XAML of one voltage drop grid column (the result is a chip)."""
    if field == "status":
        return ('<DataGridTemplateColumn IsReadOnly="True" Header="%s" Width="%d" '
                'CellTemplate="{StaticResource StatusChip}" SortMemberPath="status"/>'
                % (header, width))
    return ('<DataGridTextColumn Header="%s" Width="%d" Binding="{Binding %s}"/>'
            % (header, width, field))


def window_xaml():
    """The window's XAML with its columns, before the theme goes in."""
    with open(XAML_FILE, "rb") as f:
        text = f.read().decode("utf-8")
    columns = "\n".join(column_xaml(*c) for c in COLUMNS)
    vd_columns = "\n".join(vd_column_xaml(*c) for c in studio.VD_COLUMNS)
    text = text.replace("\nCOLUMNS\n", "\n" + columns + "\n", 1)
    return text.replace("\nVDCOLUMNS\n", "\n" + vd_columns + "\n", 1)


def themed_xaml():
    """What XamlReader loads: the window with the shared theme in amber."""
    return ui.window_xaml(window_xaml(), ACCENT)


def row_values(way):
    """{data column: text} for a ways grid row."""
    values = {"key": way.key, "label": way.label, "feeds": way.feeds, "poles": way.poles,
              "phase": way.phase, "vd": way.vd, "vd_state": studio.way_state(way)}
    for field in ed.FIELDS:
        values[field] = way.values.get(field, "")
    return values


def row_flags(way):
    return {"vd_over": bool(way.vd_over),
            "locked": not any(way.editable(f) for f in ed.FIELDS),
            "sized": bool(way.sized)}


def warnings_text(warnings, limit=2):
    if not warnings:
        return u""
    text = u"   ·   ".join(warnings[:limit])
    if len(warnings) > limit:
        text += u"   (+%d more)" % (len(warnings) - limit)
    return text


def overall_state(editor):
    """Colour of the footer dot: red, amber or green."""
    states = [studio.board_state(editor, b.id) for b in editor.boards]
    if studio.BAD in states:
        return studio.BAD
    if studio.WARN in states or editor.warnings():
        return studio.WARN
    return studio.OK


def auto_size_message(changed, messages):
    lines = []
    if changed:
        lines.append(u"%d way(s) sized from the connected load (SMDBs and DBs only). "
                     u"They are shown in green: check them, then Save to Revit." % len(changed))
    else:
        lines.append(u"Nothing changed: every SMDB and DB already matches the sizing table.")
    if messages:
        lines.append(u"")
        lines += [u"- %s" % m for m in messages]
    return u"\n".join(lines)


def spare_count(text, step):
    try:
        n = int(float(text or 0))
    except ValueError:
        n = 0
    return str(max(n + step, 0))


def _same(a, b):
    if a is b:
        return True
    try:
        return a is not None and a.Equals(b)
    except Exception:
        return False


# ---------------------------------------------------------------- window

class EditorWindow(object):
    """Plain controller around the XamlReader window (no .NET subclass, so
    nothing to register under CPython).

    actions: dict of callbacks from sld.command:
      save(editor) -> message           write the changes to Revit
      settings(sld values, vd values)   keep the settings
      report(editor, path) -> message   save the V.D report (Excel + PDF)
      report_name -> default file name of the report
    """

    def __init__(self, editor, sld_values, vd_values, actions, model_text=u""):
        self.editor = editor
        self.sld_values = dict(sld_values)
        studio.set_balance_limits(editor, self.sld_values)
        self.vd_values = dict(vd_values)
        self.actions = actions
        self.action = "close"
        self.current = None
        self.table = None
        self.rows = {}
        self.tree_items, self.tree_dots = {}, {}
        self.setting_controls = {}
        self._busy = False
        self._vd_stale = True
        self.win = ui.load_window(window_xaml(), ACCENT)
        for name in NAMES:
            setattr(self, name, self.win.FindName(name))
        self.ModelText.Text = model_text
        self._fill_choices()
        self._fill_settings()
        self._fill_tree()
        self._wire()
        self._show_states()
        self._fill_vd()

    # ------------------------------------------------------------ setup

    def _fill_choices(self):
        for key, values in ed.CHOICES.items():
            self.win.Resources["ch_%s" % key] = ui.strings(values)
        self.win.Resources["ch_fed_by"] = ui.strings(self.editor.board_names())

    def _setting_row(self, key, label, unit, kind, value):
        from System.Windows import (GridLength, HorizontalAlignment, TextWrapping, Thickness,
                                    VerticalAlignment)
        from System.Windows.Controls import (CheckBox, ColumnDefinition, ComboBox, Grid,
                                             TextBlock, TextBox)
        row = Grid()
        row.Margin = Thickness(0, 3, 0, 3)
        first, second = ColumnDefinition(), ColumnDefinition()
        first.Width = GridLength(300)
        row.ColumnDefinitions.Add(first)
        row.ColumnDefinitions.Add(second)
        if kind == "check":
            control = CheckBox()
            control.Content = label
            control.IsChecked = bool(value)
            Grid.SetColumnSpan(control, 2)
            row.Children.Add(control)
            return row, control
        text = TextBlock()
        text.Text = label + (u" (%s)" % unit if unit else u"")
        text.TextWrapping = TextWrapping.Wrap
        text.VerticalAlignment = VerticalAlignment.Center
        text.Foreground = ui.brush(self.win, "MutedBrush")
        text.Margin = Thickness(0, 0, 10, 0)
        row.Children.Add(text)
        if kind == "choice":
            control = ComboBox()
            for _, shown in studio.choices(key):
                control.Items.Add(shown)
            control.SelectedItem = studio.shown(key, value)
        else:
            control = TextBox()
            control.Text = studio.shown(key, value)
            if kind == "number":
                control.Width = 90
                control.HorizontalAlignment = HorizontalAlignment.Left
        Grid.SetColumn(control, 1)
        row.Children.Add(control)
        return row, control

    def _fill_settings(self):
        panels = {studio.SLD: self.SldSettingsPanel, studio.VD: self.VdSettingsPanel}
        values = {studio.SLD: self.sld_values, studio.VD: self.vd_values}
        for group, key, label, unit, kind in studio.SETTINGS:
            row, control = self._setting_row(key, label, unit, kind, values[group].get(key))
            panels[group].Children.Add(row)
            self.setting_controls[key] = (kind, control)

    def _tree_header(self, board):
        from System.Windows import FontWeights, Thickness, VerticalAlignment
        from System.Windows.Controls import Orientation, StackPanel, TextBlock
        from System.Windows.Shapes import Ellipse
        panel = StackPanel()
        panel.Orientation = Orientation.Horizontal
        dot = Ellipse()
        dot.Width = dot.Height = 9
        dot.Margin = Thickness(0, 0, 7, 0)
        dot.VerticalAlignment = VerticalAlignment.Center
        text = TextBlock()
        text.Text = board.name + (u"  (other model)" if board.virtual else u"")
        if board.depth == 0:
            text.FontWeight = FontWeights.SemiBold
        panel.Children.Add(dot)
        panel.Children.Add(text)
        self.tree_dots[board.id] = dot
        return panel

    def _fill_tree(self):
        from System.Windows.Controls import TreeViewItem

        def add(items, board):
            item = TreeViewItem()
            item.Header = self._tree_header(board)
            item.Tag = board.id
            item.IsExpanded = True
            items.Add(item)
            self.tree_items[board.id] = item
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
        self.Steps.SelectionChanged += self.on_step
        self.VdProblemsOnly.Click += self.on_vd_filter
        self.VdSearch.TextChanged += self.on_vd_filter
        self.VdGrid.MouseDoubleClick += self.on_vd_open
        self.SaveButton.Click += self.on_save_click
        self.AutoSizeButton.Click += self.on_auto_size
        self.ReportButton.Click += self.on_report
        self.GenerateButton.Click += self.on_generate
        self.CloseButton.Click += self.on_close_click
        self.AddSpare.Click += self.on_add_spare
        self.RemoveSpare.Click += self.on_remove_spare
        self.AddSpace.Click += self.on_add_space
        self.RemoveSpace.Click += self.on_remove_space
        self.ApplySettings.Click += self.on_apply_settings
        self.win.Closing += self.on_closing
        for name, _ in BOARD_CONTROLS:
            control = getattr(self, name)
            control.LostKeyboardFocus += self.on_board_field
            control.KeyDown += self.on_board_key
            if hasattr(control, "DropDownClosed"):
                control.DropDownClosed += self.on_board_field

    def show(self):
        self.win.ShowDialog()
        return self.action, self.sld_values, self.vd_values

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

    def _status(self, text):
        """A line in the footer, painted before a long step runs."""
        self.WarningsText.Text = text
        ui.pump(self.win)

    def _paint_chip(self, chip, text_block, state, text):
        fg, bg = ui.state_brushes(self.win, state)
        chip.Background = bg
        text_block.Foreground = fg
        text_block.Text = text

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
            self.FedBy.IsEnabled = self.editor.fed_by_editable(board_id)
            self.TxVd.IsEnabled = self.editor.has_incoming(board_id)
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
        self.PreviewText.Text = u"Click a way to see how it prints on the SLD."
        self._show_tiles()
        self._show_states()

    def _show_tiles(self):
        if self.current is None:
            return
        s = studio.board_summary(self.editor, self.current)
        self.KpiConnected.Text = s["connected"]
        self.KpiDemand.Text = s["demand"]
        self.KpiIncomer.Text = s["incomer"]
        self.KpiVd.Text = s["worst_vd"]
        self.KpiVd.Foreground = ui.state_brushes(self.win, s["worst_state"])[0] \
            if s["worst_state"] else ui.brush(self.win, "TextBrush")
        self.KpiBalance.Text = s["balance"]
        self.KpiBalance.Foreground = ui.state_brushes(self.win, s["balance_state"])[0] \
            if s["balance_state"] else ui.brush(self.win, "TextBrush")
        self.KpiBalanceSub.Text = s["balance_sub"]
        self.BoardWays.Text = s["ways"]
        self._paint_chip(self.BoardChip, self.BoardChipText, s["state"],
                         STATE_TEXT.get(s["state"], u""))

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
        self._vd_stale = True
        self._show_tiles()
        self._show_states()

    def _show_states(self):
        """Tree dots, the footer line and the V.D tab's dot."""
        for board in self.editor.boards:
            dot = self.tree_dots.get(board.id)
            if dot is not None:
                dot.Fill = ui.state_brushes(self.win, studio.board_state(self.editor,
                                                                         board.id))[0]
        warnings = self.editor.warnings()
        self.WarningsText.Text = warnings_text(warnings) or u"No problems found."
        self.WarningsText.ToolTip = u"\n".join(warnings) if warnings else None
        self.StatusDot.Fill = ui.state_brushes(self.win, overall_state(self.editor))[0]
        text, state = studio.vd_tab_header(self.editor)
        self.VdTabText.Text = text
        self.VdDot.Fill = ui.state_brushes(self.win, state)[0]

    def _row_key(self, item):
        try:
            return u"%s" % item.Row["key"]
        except Exception:
            return None

    # ------------------------------------------------------------ voltage drop tab

    def _fill_vd(self):
        from System import String
        from System.Data import DataTable
        s = studio.vd_summary(self.editor)
        self.VdCables.Text = s["cables"]
        self.VdOk.Text = s["ok"]
        self.VdFailed.Text = s["failed"]
        self.VdIncomplete.Text = s["incomplete"]
        self.VdWorst.Text = s["worst"]
        self.VdWorst.Foreground = ui.state_brushes(self.win, s["worst_state"])[0] \
            if s["worst_state"] else ui.brush(self.win, "TextBrush")
        self.VdWorstWhere.Text = s["worst_where"]
        self.VdFixes.Text = u"\n".join(u"•  %s" % f for f in s["fixes"]) or \
            u"Nothing to fix: every cable passes."
        table = DataTable("Cables")
        names = ("key", "state") + tuple(c[0] for c in studio.VD_COLUMNS)
        for name in names:
            table.Columns.Add(name, String).DefaultValue = u""
        for values in studio.vd_rows(self.editor, bool(self.VdProblemsOnly.IsChecked),
                                     self.VdSearch.Text):
            row = table.NewRow()
            for name in names:
                row[name] = u"%s" % (values.get(name) or u"")
            table.Rows.Add(row)
        table.AcceptChanges()
        self.VdGrid.ItemsSource = table.DefaultView
        self._vd_stale = False

    def on_step(self, sender, args):
        if not _same(args.OriginalSource, self.Steps):
            return       # a combo or grid inside a tab
        if self._vd_stale and _same(self.Steps.SelectedItem, self.VdTab):
            self._safe(self._fill_vd)

    def on_vd_filter(self, sender, args):
        self._safe(self._fill_vd)

    def on_vd_open(self, sender, args):
        """Double-click a cable: show the board it starts from."""
        item = self.VdGrid.SelectedItem
        if item is None or self.editor.result is None:
            return
        key = u"%s" % item.Row["key"]
        row = next((r for r in self.editor.result.rows() if u"%s" % r.feeder.id == key), None)
        board_id = row.feeder.source_id if row is not None else None
        tree_item = self.tree_items.get(board_id)
        if tree_item is None:
            return
        self.Steps.SelectedItem = self.BoardsTab
        tree_item.IsSelected = True
        tree_item.BringIntoView()

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
        field = next(f for n, f in BOARD_CONTROLS if _same(getattr(self, n), sender))
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
            self._vd_stale = True
            self._show_tiles()
            self._show_states()

    def _step_spares(self, step, field="spares"):
        self._commit()
        board = self.editor.board(self.current)
        self.editor.set_board(self.current, field, spare_count(board.values[field], step))
        self._show_board(self.current)

    def on_add_spare(self, sender, args):
        if self.current is not None:
            self._safe(self._step_spares, 1)

    def on_remove_spare(self, sender, args):
        if self.current is not None:
            self._safe(self._step_spares, -1)

    def on_add_space(self, sender, args):
        if self.current is not None:
            self._safe(self._step_spares, 1, "spaces")

    def on_remove_space(self, sender, args):
        if self.current is not None:
            self._safe(self._step_spares, -1, "spaces")

    def on_auto_size(self, sender, args):
        self._commit()
        self._safe(self._auto_size)

    def _auto_size(self):
        changed, messages = self.editor.auto_size()
        if self.current is not None:
            self._show_board(self.current)
        self._fill_vd()
        self._alert(auto_size_message(changed, messages))

    def on_save_click(self, sender, args):
        self._commit()
        self._safe(self._save)

    def _save(self):
        reload = any(c.kind == "fed_by" for c in self.editor.changes())
        self._status(u"Saving to Revit...")
        message = self.actions["save"](self.editor)
        self._show_board(self.current)
        if reload:
            message += u"\n\nFed from changed: the window opens again with the new feeds."
        self._alert(message)
        if reload:
            self.action = "reload"
            self.win.Close()

    def on_report(self, sender, args):
        self._commit()
        self._safe(self._report)

    def _report(self):
        from Microsoft.Win32 import SaveFileDialog
        if self.editor.result is None or not list(self.editor.result.rows()):
            self._alert(u"Nothing to report: no panel is fed from another panel or a "
                        u"transformer, and no final circuit has a length.")
            return
        dialog = SaveFileDialog()
        dialog.Filter = "Excel workbook (*.xlsx)|*.xlsx"
        dialog.FileName = self.actions["report_name"]
        if not dialog.ShowDialog(self.win):
            return
        self._status(u"Saving the voltage drop report (Excel, then PDF)...")
        try:
            message = self.actions["report"](self.editor, dialog.FileName)
        finally:
            self._show_states()
        self._alert(message)

    def on_apply_settings(self, sender, args):
        self._commit()
        self._safe(self._apply_settings)

    def _apply_settings(self):
        form = {}
        for key, (kind, control) in self.setting_controls.items():
            if kind == "check":
                form[key] = bool(control.IsChecked)
            elif kind == "choice":
                form[key] = u"%s" % (control.SelectedItem or control.Text or u"")
            else:
                form[key] = control.Text
        sld_values, vd_values, errors = studio.apply_settings(self.sld_values,
                                                              self.vd_values, form)
        if errors:
            self._alert(u"Not saved:\n\n" + u"\n".join(errors))
            return
        reload = studio.needs_reload(self.sld_values, self.vd_values, sld_values, vd_values)
        self.actions["settings"](sld_values, vd_values)
        self.sld_values, self.vd_values = sld_values, vd_values
        studio.set_balance_limits(self.editor, sld_values)
        if reload:
            if self.editor.dirty():
                answer = self._alert(u"These settings are read with the model, so the window "
                                     u"opens again.\n\nSave your changes to Revit first?",
                                     ask=True)
                if answer == "cancel":
                    return
                if answer == "yes":
                    self.actions["save"](self.editor)
                    self.editor.mark_saved()
            self.action = "reload"
            self.win.Close()
            return
        from vdrop import settings as vd_settings
        self.editor.set_vd_settings(vd_settings.calc_settings(vd_values))
        if self.current is not None:
            self._show_board(self.current)
        self._fill_vd()
        self.SettingsNote.Text = u"Settings saved."

    def on_generate(self, sender, args):
        self._commit()
        self.action = "generate"
        self.win.Close()

    def on_close_click(self, sender, args):
        self.win.Close()

    def on_closing(self, sender, args):
        self._commit()
        if self.action in ("generate", "reload") or not self.editor.dirty():
            return
        answer = self._alert("Save your changes to Revit before closing?", ask=True)
        if answer == "cancel":
            args.Cancel = True
        elif answer == "yes":
            self._safe(lambda: self.actions["save"](self.editor))


def show_editor(editor, sld_values, vd_values, actions, model_text=u""):
    """Show the window (modal). Returns (action, sld values, vd values);
    action is 'generate', 'reload' (read the model again: a Fed from or a
    setting read with the model changed) or 'close'."""
    return EditorWindow(editor, sld_values, vd_values, actions, model_text).show()
