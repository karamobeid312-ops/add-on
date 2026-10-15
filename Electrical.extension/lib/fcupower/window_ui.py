# -*- coding: utf-8 -*-
"""The FCU Power window (WPF), in the Electrical tab's shared look.

Works with pyRevit's IronPython 2.7 and CPython 3 engines: the XAML is
loaded with XamlReader, events are wired here and the grid shows a
System.Data.DataTable. The rules live in fcupower.schedule / match; the
Revit side comes in as callbacks from fcupower.command.
"""
from __future__ import division

import os

import elecui as ui
from fcupower import match as m
from fcupower import schedule, xlsxread

XAML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window.xaml")
TITLE = "FCU Power"
ACCENT = "#2F7FD8"              # mechanical blue
NAMES = ("ModelText", "StatusDot", "StatusText", "CloseButton", "WriteButton",
         "BrowseButton", "FileText", "SheetList", "SheetTitle", "TagCombo", "RoomCombo",
         "PowerCombo", "UnitCombo", "SheetInfo", "FamilyList", "KpiWrite", "KpiSame",
         "KpiCheck", "KpiBad", "KpiUnused", "ShowCombo", "SearchText", "ResultGrid",
         "TagParamCombo", "SocketTypeCombo", "AddButton", "FloorCombo", "PanelCombo",
         "WireTypeCombo", "WireTagCombo", "CircuitButton", "CircuitInfo")
TEXT_COLUMNS = ("key", "tag", "room", "space", "where", "now", "new", "status", "state")
NONE_CHOICE = u"(none)"
ALL_FLOORS = u"All floors"
SHOW = ((u"all", u"All FCUs"), (u"write", u"To write"), (u"check", u"Check (amber)"),
        (u"bad", u"Problems (red)"), (u"same", u"Already set"),
        (u"unused", u"Schedule rows not in the model"),
        (u"nosocket", u"Linked FCUs with no socket"))


def window_xaml():
    with open(XAML_FILE, "rb") as f:
        return f.read().decode("utf-8")


def fcu_values(fcu):
    rows = fcu.rows
    return {
        "key": u"%d" % fcu.key, "room": fcu.room,
        "tag": (fcu.tag or u"(empty)") + (u"  (%.1f m)" % fcu.linked_distance
                                          if fcu.tag and m.NO_TAG[0].startswith(u"No linked")
                                          and fcu.linked_distance is not None else u""),
        "space": u", ".join(sorted(set(r.room for r in rows if r.room))),
        "where": u", ".join(r.where for r in rows[:2]) + (u" ..." if len(rows) > 2 else u""),
        "now": m.watts_text(fcu.current), "new": m.watts_text(fcu.watts),
        "status": fcu.status, "state": fcu.state,
    }


def row_values(row):
    return {"key": u"row:%s:%d" % (row.sheet, row.number), "tag": row.tag, "room": u"",
            "space": row.room, "where": row.where, "now": u"",
            "new": m.watts_text(row.watts), "status": u"No FCU with this tag in the model",
            "state": m.WARN}


def shown(fcu, show):
    if show == u"write":
        return fcu.write
    if show == u"check":
        return fcu.state == m.WARN
    if show == u"bad":
        return fcu.state == m.BAD
    if show == u"same":
        return fcu.status.startswith(u"Already set")
    return True


def found(values, search):
    if not search:
        return True
    search = search.lower()
    return any(search in (values.get(k) or u"").lower()
               for k in ("tag", "room", "space", "where", "status"))


class FcuWindow(object):
    """Plain controller around the XamlReader window.

    revit: dict of callbacks from fcupower.command:
      families -> [revit_fcu.Family]
      read(families, progress) -> [match.Fcu]   FCUs of the ticked families
      write(fcus) -> (written, [failures])
      path -> the schedule opened last time
      keep_path(path)
    """

    def __init__(self, revit, model_text=u""):
        self.revit = revit
        self.families = revit["families"]
        kept = set(revit.get("families_ticked") or [])
        names = set(f.name for f in self.families)
        self.ticked_families = (kept & names) or set(f.name for f in self.families if f.default)
        self.sheets = []
        self.ticked_sheets = set()
        self.current = None             # the sheet whose columns are shown
        self.fcus, self.unused = [], []
        self.overrides = {}             # FCU key -> write ticked by hand
        self.tag_param = None           # picked by hand; None: the best match
        self.units = revit.get("units") or []   # linked FCUs (x, y, z, tag)
        self.missing = []               # indexes in units: in the schedule, no socket
        self.socket_types = []
        self.levels = revit.get("levels") or []         # [(name, elevation ft)] low to high
        self.all_missing = []
        self.tag_params = []
        self.table = None
        self._quiet = False
        self.win = ui.load_window(window_xaml(), ACCENT)
        for name in NAMES:
            setattr(self, name, self.win.FindName(name))
        self.ModelText.Text = model_text
        for _, text in SHOW:
            self.ShowCombo.Items.Add(text)
        self.ShowCombo.SelectedIndex = 0
        for unit in schedule.UNITS + (schedule.NO_UNIT,):
            self.UnitCombo.Items.Add(unit)
        self._fill_families()
        self.FloorCombo.Items.Add(ALL_FLOORS)
        for name, _ in self.levels:
            self.FloorCombo.Items.Add(name)
        names = [n for n, _ in self.levels]
        active = revit.get("active_level")
        self.FloorCombo.SelectedIndex = names.index(active) + 1 if active in names else 0
        self._fill_circuit_choices()
        self._wire()
        path = revit.get("path") or u""
        if path and os.path.isfile(path):
            self._open(path, quiet=True)
        else:
            self._show_sheet(None)
            self._status(u"Pick the mechanical schedule (.xlsx) to start.", "")
        self.refresh()

    # ------------------------------------------------------------ setup

    def _wire(self):
        self.BrowseButton.Click += self.on_browse
        self.CloseButton.Click += lambda s, e: self.win.Close()
        self.WriteButton.Click += self.on_write
        self.AddButton.Click += self.on_add
        self.CircuitButton.Click += self.on_circuit
        self.FloorCombo.SelectionChanged += self.on_floor
        self.SheetList.SelectionChanged += self.on_sheet
        for combo in (self.TagCombo, self.RoomCombo, self.PowerCombo, self.UnitCombo):
            combo.SelectionChanged += self.on_column
        self.ShowCombo.SelectionChanged += lambda s, e: self._fill_grid()
        self.TagParamCombo.SelectionChanged += self.on_tag_param
        self.SearchText.TextChanged += lambda s, e: self._fill_grid()

    def _check_item(self, text, tag, ticked, handler):
        from System.Windows.Controls import CheckBox, ListBoxItem
        from System.Windows import Thickness
        box = CheckBox()
        box.Content = text
        box.Tag = tag
        box.IsChecked = ticked
        box.Margin = Thickness(0, 2, 0, 2)
        box.Checked += handler
        box.Unchecked += handler
        item = ListBoxItem()
        item.Content = box
        item.Tag = tag
        return item

    def _fill_socket_types(self):
        names = sorted(self.ticked_families)
        types = self.revit["socket_types"](names) if "socket_types" in self.revit else {}
        current = self.SocketTypeCombo.SelectedItem
        current = u"%s" % current if current is not None else None
        self.socket_types = sorted(types)
        self.SocketTypeCombo.Items.Clear()
        for label in self.socket_types:
            self.SocketTypeCombo.Items.Add(label)
        pick = current if current in self.socket_types else \
            self.revit["default_type"](self.socket_types, names) if self.socket_types else None
        if pick in self.socket_types:
            self.SocketTypeCombo.SelectedIndex = self.socket_types.index(pick)

    def _fill_families(self):
        self._fill_socket_types()
        self.FamilyList.Items.Clear()
        for fam in self.families:
            text = u"%s   (%d, %d with Real_Power_W)" % (fam.name, len(fam.elements), fam.with_param)
            self.FamilyList.Items.Add(self._check_item(text, fam.name, fam.name in self.ticked_families,
                                                       self.on_family))

    def _fill_sheets(self):
        self._quiet = True
        try:
            self.SheetList.Items.Clear()
            for sheet in self.sheets:
                if sheet.usable:
                    text = u"%s   (%d FCU rows)" % (sheet.name, len(sheet.fcu_rows()))
                else:
                    text = u"%s   (no tag column found)" % sheet.name
                item = self._check_item(text, sheet.name, sheet.name in self.ticked_sheets,
                                        self.on_sheet_tick)
                item.Content.IsEnabled = sheet.usable
                self.SheetList.Items.Add(item)
            first = next((i for i, s in enumerate(self.sheets) if s.usable), None)
            if first is not None:
                self.SheetList.SelectedIndex = first
        finally:
            self._quiet = False
        self._show_sheet(self.sheets[first] if first is not None else None)

    def _show_sheet(self, sheet):
        self.current = sheet
        self._quiet = True
        try:
            for combo in (self.TagCombo, self.RoomCombo, self.PowerCombo):
                combo.Items.Clear()
            enabled = sheet is not None and sheet.usable
            for combo in (self.TagCombo, self.RoomCombo, self.PowerCombo, self.UnitCombo):
                combo.IsEnabled = enabled
            if not enabled:
                self.SheetTitle.Text = u"Columns" if sheet is None else u"%s: no FCU tag column" % sheet.name
                self.SheetInfo.Text = u""
                self.UnitCombo.SelectedIndex = -1
                return
            self.SheetTitle.Text = u"Columns of %s" % sheet.name
            self.RoomCombo.Items.Add(NONE_CHOICE)
            self.PowerCombo.Items.Add(NONE_CHOICE)
            for col in sheet.columns:
                self.TagCombo.Items.Add(col.shown)
                self.RoomCombo.Items.Add(col.shown)
                self.PowerCombo.Items.Add(col.shown)
            self.TagCombo.SelectedItem = sheet.tag.shown
            self.RoomCombo.SelectedItem = sheet.room.shown if sheet.room else NONE_CHOICE
            self.PowerCombo.SelectedItem = sheet.power.shown if sheet.power else NONE_CHOICE
            self.UnitCombo.SelectedItem = sheet.unit
            self._sheet_info(sheet)
        finally:
            self._quiet = False

    def _sheet_info(self, sheet):
        rows = sheet.fcu_rows()
        with_power = sum(1 for r in rows if r.watts is not None)
        text = u"%d FCU rows, %d with a power in W" % (len(rows), with_power)
        if sheet.unit == schedule.NO_UNIT and sheet.power is not None:
            text += u". Pick the unit of the power column (kW or W)."
        elif sheet.power is not None and sheet.power.unit and sheet.power.unit not in schedule.UNITS:
            text += u". The header says %s: check the column." % sheet.power.unit
        if sheet.qty is not None:
            text += u" Power is taken per unit (each FCU gets the row's value)."
        self.SheetInfo.Text = text

    # ------------------------------------------------------------ helpers

    def _status(self, text, state):
        self.StatusText.Text = text
        fg, _ = ui.state_brushes(self.win, state)
        self.StatusDot.Fill = fg
        ui.pump(self.win)

    def _alert(self, text, title=TITLE):
        from System.Windows import MessageBox
        MessageBox.Show(self.win, text, title)

    def _open(self, path, quiet=False):
        if path.lower().endswith(u".xls"):
            self._alert(u"This is an old .xls file. Open it in Excel and save it as .xlsx, "
                        u"then pick the .xlsx.")
            return False
        self._status(u"Reading %s..." % os.path.basename(path), "")
        try:
            self.sheets = schedule.sheets(xlsxread.read(path))
        except xlsxread.NotXlsx:
            if not quiet:
                self._alert(u"Could not read this file as an Excel workbook (.xlsx):\n%s" % path)
            return False
        except Exception as error:
            if not quiet:
                self._alert(u"Could not read the schedule:\n%s\n\nIf Excel shows an error for it, "
                            u"fix it there and save again." % error)
            return False
        self.FileText.Text = path
        self.ticked_sheets = set(s.name for s in self.sheets if s.usable and s.fcu_rows())
        self._fill_sheets()
        try:
            self.revit["keep_path"](path)
        except Exception:
            pass
        return True

    def schedule_rows(self):
        rows = []
        for sheet in self.sheets:
            if sheet.usable and sheet.name in self.ticked_sheets:
                rows += sheet.fcu_rows()
        return rows

    def refresh(self, reread=True):
        """Read the FCUs (rooms are cached) and match them again."""
        if reread:
            fams = [f for f in self.families if f.name in self.ticked_families]
            total = sum(len(f.elements) for f in fams)
            if total:
                self._status(u"Reading %d FCUs and finding their rooms..." % total, "")

            def progress(done, count):
                self._status(u"Finding the room of each FCU... %d / %d" % (done, count), "")
            self.fcus = self.revit["read"](fams, progress)
        rows = self.schedule_rows()
        self._fill_tag_params(rows)
        self.unused = m.match(self.fcus, rows)
        linked = m.NO_TAG[0].startswith(u"No linked")
        self.all_missing = m.missing_sockets(self.units, self.fcus, rows) if linked else []
        self.by_tag = m.index_rows(rows)
        self._fill_missing(grid=False)
        for fcu in self.fcus:
            fcu.can = fcu.write
            key = fcu.key
            if fcu.can and key in self.overrides:
                fcu.write = self.overrides[key]
        self._fill_tiles()
        self._fill_grid()

    def _fill_tag_params(self, rows):
        """List the FCUs' text parameters (best match first) and read the
        tags from the one picked, or the best one."""
        self.tag_params = m.tag_parameters(self.fcus, rows)
        names = [n for n, _, _ in self.tag_params]
        name = self.tag_param if self.tag_param in names else names[0]
        self._quiet = True
        try:
            self.TagParamCombo.Items.Clear()
            for n, filled, found in self.tag_params:
                self.TagParamCombo.Items.Add(u"%s   (%d filled, %d in schedule)" % (n, filled, found))
            self.TagParamCombo.SelectedIndex = names.index(name)
        finally:
            self._quiet = False
        m.use_tag_parameter(self.fcus, name)

    def _fill_tiles(self):
        fcus = self.floor_fcus()
        s = m.summary(fcus, self.unused)
        self.KpiWrite.Text = u"%d" % sum(1 for f in fcus if f.write)
        self.KpiSame.Text = u"%d" % s["same"]
        self.KpiCheck.Text = u"%d" % s["check"]
        self.KpiBad.Text = u"%d" % s["bad"]
        self.KpiUnused.Text = u"%d" % s["unused"]
        if not self.sheets:
            return
        if not fcus:
            self._status(u"No FCU of the ticked families on this floor.", "warn")
        elif s["bad"]:
            self._status(u"%d FCU(s) can't be written: see the red rows." % s["bad"], "bad")
        elif s["check"]:
            self._status(u"%d FCU(s) to check (amber): matched on the tag only." % s["check"], "warn")
        else:
            self._status(u"Every FCU matches the schedule.", "ok")

    def _fill_grid(self):
        from System import Boolean, String
        from System.Data import DataTable
        show = SHOW[max(self.ShowCombo.SelectedIndex, 0)][0]
        search = (self.SearchText.Text or u"").strip()
        table = DataTable("Fcus")
        for name in TEXT_COLUMNS:
            table.Columns.Add(name, String).DefaultValue = u""
        table.Columns.Add("write", Boolean).DefaultValue = False
        table.Columns.Add("can", Boolean).DefaultValue = False
        items = []
        if show == u"unused":
            items = [(row_values(r), False, False) for r in self.unused]
        elif show == u"nosocket":
            items = [(self._missing_values(i), False, False) for i in self.missing]
        else:
            order = {m.BAD: 0, m.WARN: 1, m.OK: 2}
            for fcu in sorted(self.floor_fcus(), key=lambda f: (order.get(f.state, 3), m.tokens(f.tag))):
                if shown(fcu, show):
                    items.append((fcu_values(fcu), bool(fcu.write), bool(fcu.can)))
        for values, write, can in items:
            if not found(values, search):
                continue
            row = table.NewRow()
            for name in TEXT_COLUMNS:
                row[name] = String(values.get(name) or u"")
            row["write"] = write
            row["can"] = can
            table.Rows.Add(row)
        table.AcceptChanges()
        table.ColumnChanged += self.on_tick
        self.table = table
        self.ResultGrid.ItemsSource = table.DefaultView

    def _floor_range(self):
        """(bottom, top) in ft of the floor picked, or None for all floors."""
        name = self.FloorCombo.SelectedItem
        name = u"%s" % name if name is not None else ALL_FLOORS
        names = [n for n, _ in self.levels]
        if name not in names:
            return None
        i = names.index(name)
        bottom = self.levels[i][1]
        top = next((z for _, z in self.levels[i + 1:] if z > bottom + 1.0 / 0.3048), bottom + 6.0 / 0.3048)
        return bottom - 0.3 / 0.3048, top

    def floor_fcus(self):
        """The FCUs (sockets) of the floor picked."""
        span = self._floor_range()
        if span is None:
            return self.fcus
        return [f for f in self.fcus if f.z is not None and span[0] <= f.z < span[1]]

    def _fill_circuit_choices(self):
        if "panels" not in self.revit:
            return
        for name in self.revit["panels"]():
            self.PanelCombo.Items.Add(name)
        last = self.revit.get("panel") or u""
        if last:
            self.PanelCombo.Text = last
        for combo, key in ((self.WireTypeCombo, "wire_types"), (self.WireTagCombo, "tag_types")):
            names, best = self.revit[key]()
            combo.Items.Add(NONE_CHOICE)
            for name in names:
                combo.Items.Add(name)
            combo.SelectedIndex = names.index(best) + 1 if best in names else 0

    def to_circuit(self):
        """The outlets of the floor picked that are on no circuit yet."""
        return [f for f in self.floor_fcus() if not f.circuited]

    def _fill_circuit_info(self):
        n = len(self.to_circuit())
        self.CircuitButton.Content = u"Circuit + wire (%d)" % n
        self.CircuitButton.IsEnabled = bool(n)
        floor = u"%s" % (self.FloorCombo.SelectedItem or ALL_FLOORS)
        self.CircuitInfo.Text = (u"%d outlet(s) of %s with no circuit. Each gets its own circuit on "
                                 u"the panel, a home-run wire towards it and the wire tag, in the "
                                 u"floor's plan." % (n, floor))

    def _fill_missing(self, grid=True):
        span = self._floor_range()
        self.missing = [i for i in self.all_missing
                        if span is None or span[0] <= self.units[i][2] < span[1]]
        self.AddButton.Content = u"Add missing sockets (%d)" % len(self.missing)
        self.AddButton.IsEnabled = bool(self.missing)
        self._fill_circuit_info()
        if grid:
            self._fill_grid()

    def _missing_values(self, index):
        tag = self.units[index][3]
        rows = self.by_tag.get(m.tag_key(tag), [])
        watts = next((r.watts for r in rows if r.watts is not None), None)
        return {"key": u"unit:%d" % index, "tag": tag, "room": u"",
                "space": u", ".join(sorted(set(r.room for r in rows if r.room))),
                "where": u", ".join(r.where for r in rows[:2]), "now": u"",
                "new": m.watts_text(watts),
                "status": u"No socket within 3 m: Add missing sockets puts one on the slab",
                "state": m.WARN}

    # ------------------------------------------------------------ events

    def on_circuit(self, sender, args):
        from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
        todo = self.to_circuit()
        panel = (self.PanelCombo.Text or u"").strip()
        names = [u"%s" % n for n in self.PanelCombo.Items]
        if panel not in names:
            self._alert(u"Pick the panel the FCU outlets are fed from.")
            return

        def picked(combo):
            item = combo.SelectedItem
            text = u"%s" % item if item is not None else NONE_CHOICE
            return None if text == NONE_CHOICE else text
        wire, tag = picked(self.WireTypeCombo), picked(self.WireTagCombo)
        floor = u"%s" % (self.FloorCombo.SelectedItem or ALL_FLOORS)
        answer = MessageBox.Show(
            self.win, u"Circuit %d outlet(s) of %s to %s, one circuit each,%s?"
            % (len(todo), floor, panel,
               u" with a home-run wire (%s) and tag (%s)" % (wire, tag or u"no tag") if wire
               else u" without wires"),
            TITLE, MessageBoxButton.YesNo)
        if answer != MessageBoxResult.Yes:
            return
        self._status(u"Circuiting %d outlet(s) to %s..." % (len(todo), panel), "")
        try:
            made, wired, tagged, failed = self.revit["circuit"](
                [(f.key, f.tag or u"id %d" % f.key) for f in todo], panel, wire, tag)
        except Exception as error:
            self._alert(u"Nothing was circuited:\n%s" % error)
            return
        try:
            self.revit["keep_panel"](panel)
        except Exception:
            pass
        self.refresh()
        text = u"%d circuit(s) made on %s, %d wire(s) and %d tag(s) drawn." % (made, panel, wired, tagged)
        if failed:
            text += u"\n\nProblems:\n" + u"\n".join(u"- %s" % f for f in failed[:30])
            if len(failed) > 30:
                text += u"\n(+%d more)" % (len(failed) - 30)
        self._alert(text)

    def on_floor(self, sender, args):
        self._fill_missing(grid=False)
        self._fill_tiles()
        self._fill_grid()

    def on_add(self, sender, args):
        from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
        label = self.SocketTypeCombo.SelectedItem
        if not self.missing:
            return
        if label is None:
            self._alert(u"Pick the socket type first (a face-based or level-based type of the "
                        u"ticked families).")
            return
        label = u"%s" % label
        floor = u"%s" % (self.FloorCombo.SelectedItem or ALL_FLOORS)
        answer = MessageBox.Show(
            self.win, u"Add %d socket(s) of type\n%s\non the slab above each FCU of %s that has none?\n\n"
            u"Their Real_Power_W is filled when you press Write to Revit."
            % (len(self.missing), label, floor), TITLE, MessageBoxButton.YesNo)
        if answer != MessageBoxResult.Yes:
            return
        self._status(u"Reading the slabs and adding %d socket(s)..." % len(self.missing), "")
        try:
            placed, failed = self.revit["add"]([self.units[i] for i in self.missing], label,
                                              sorted(self.ticked_families))
        except Exception as error:
            self._alert(u"No socket was added:\n%s" % error)
            return
        self.families = self.revit["reload_families"]()
        self._fill_families()
        self.refresh()
        text = u"%d socket(s) added on the slab. They are listed now; press Write to Revit " \
            u"to fill their Real_Power_W." % placed
        if failed:
            text += u"\n\nNot added:\n" + u"\n".join(u"- %s" % f for f in failed[:30])
            if len(failed) > 30:
                text += u"\n(+%d more)" % (len(failed) - 30)
        self._alert(text)

    def on_browse(self, sender, args):
        from Microsoft.Win32 import OpenFileDialog
        dialog = OpenFileDialog()
        dialog.Filter = u"Excel workbook (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|Old Excel (*.xls)|*.xls"
        current = self.FileText.Text
        if current and os.path.isdir(os.path.dirname(current)):
            dialog.InitialDirectory = os.path.dirname(current)
        if not dialog.ShowDialog(self.win):
            return
        if self._open(dialog.FileName):
            self.overrides = {}
            self.refresh(reread=False)

    def on_sheet(self, sender, args):
        if self._quiet:
            return
        item = self.SheetList.SelectedItem
        if item is None:
            return
        sheet = next((s for s in self.sheets if s.name == item.Tag), None)
        self._show_sheet(sheet)

    def on_sheet_tick(self, sender, args):
        if self._quiet:
            return
        if sender.IsChecked:
            self.ticked_sheets.add(sender.Tag)
        else:
            self.ticked_sheets.discard(sender.Tag)
        self.refresh(reread=False)

    def on_family(self, sender, args):
        if sender.IsChecked:
            self.ticked_families.add(sender.Tag)
        else:
            self.ticked_families.discard(sender.Tag)
        keep = self.revit.get("keep_families")
        if keep is not None:
            keep(self.ticked_families)
        self._fill_socket_types()
        self.refresh()

    def on_column(self, sender, args):
        sheet = self.current
        if self._quiet or sheet is None or not sheet.usable:
            return

        def pick(combo):
            text = combo.SelectedItem
            return next((c for c in sheet.columns if c.shown == text), None)
        sheet.tag = pick(self.TagCombo) or sheet.tag
        sheet.room = pick(self.RoomCombo)
        power = pick(self.PowerCombo)
        if sender is self.PowerCombo and power is not None:
            sheet.power = power
            self._quiet = True
            try:
                sheet.unit = sheet.guess_unit(power)
                self.UnitCombo.SelectedItem = sheet.unit
            finally:
                self._quiet = False
        else:
            sheet.power = power
            unit = self.UnitCombo.SelectedItem
            sheet.unit = u"%s" % unit if unit is not None else schedule.NO_UNIT
        self._sheet_info(sheet)
        for item in self.SheetList.Items:
            if item.Tag == sheet.name:
                item.Content.Content = u"%s   (%d FCU rows)" % (sheet.name, len(sheet.fcu_rows()))
        self.refresh(reread=False)

    def on_tag_param(self, sender, args):
        if self._quiet:
            return
        index = self.TagParamCombo.SelectedIndex
        if 0 <= index < len(self.tag_params):
            self.tag_param = self.tag_params[index][0]
            self.overrides = {}
            self.refresh(reread=False)

    def on_tick(self, sender, args):
        if args.Column.ColumnName != "write":
            return
        key = u"%s" % args.Row["key"]
        if not key.isdigit():
            return
        value = bool(args.ProposedValue)
        self.overrides[int(key)] = value
        for fcu in self.fcus:
            if fcu.key == int(key) and fcu.can:
                fcu.write = value
        self.KpiWrite.Text = u"%d" % sum(1 for f in self.floor_fcus() if f.write)

    def on_write(self, sender, args):
        todo = [f for f in self.floor_fcus() if f.write]
        if not todo:
            self._alert(u"Nothing to write: no FCU is ticked.")
            return
        self._status(u"Writing Real_Power_W on %d FCU(s)..." % len(todo), "")
        try:
            written, failed = self.revit["write"](todo)
        except Exception as error:
            self._alert(u"Nothing was written:\n%s" % error)
            self.refresh()
            return
        self.overrides = {}
        self.refresh()
        text = u"Real_Power_W written on %d FCU(s)." % written
        if failed:
            text += u"\n\nNot written:\n" + u"\n".join(u"- %s" % f for f in failed[:30])
            if len(failed) > 30:
                text += u"\n(+%d more)" % (len(failed) - 30)
        self._alert(text)

    def show(self):
        self.win.ShowDialog()


def show_window(revit, model_text=u""):
    FcuWindow(revit, model_text).show()
