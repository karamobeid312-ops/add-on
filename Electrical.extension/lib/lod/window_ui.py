# -*- coding: utf-8 -*-
"""The LOD Studio window (WPF), in the Electrical tab's shared look: every
LOD tool in one window, one tab per step.

Works with pyRevit's IronPython 2.7 and CPython 3 engines: the XAML is
loaded with XamlReader, events are wired here and the grids show a
System.Data.DataTable. The rows come from lod.studio; the Revit side comes in
as callbacks from lod.command.
"""
from __future__ import division

import os

import elecui as ui
from lod import export, keyplan, studio
from lod.compare import compare

XAML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window.xaml")
TITLE = "LOD Studio"
ACCENT = "#6A55C8"              # LOD violet
NAMES = ("ModelText", "StatusDot", "StatusText", "CloseButton", "SetupButton", "SearchText",
         "ReloadButton", "BrowseButton", "FileText", "Steps",
         "CreateTabText", "CreateButton", "CreateKeyplans", "CreateViews", "TitleBlockCombo",
         "CreateGrid",
         "CompareTabText", "KpiDrawings", "KpiMatched", "KpiChanges", "KpiMissing", "KpiExtra",
         "SyncButton", "CompareGrid",
         "ViewsTabText", "PlaceButton", "ViewsShowCombo", "ViewsGrid",
         "KeyTabText", "KeyButton", "KeyShowCombo", "KeyGrid",
         "ExportUpdate", "ExportNew", "ExportButton", "ExportGrid",
         "SetupPanel", "SetupDone", "PrefixText", "RevText", "AreaText", "RulesButton",
         "RulesResetButton", "RulesInfo", "ParamsButton", "ParamsGrid",
         "TickSelectedButton", "UntickSelectedButton", "TickAllButton", "UntickAllButton")
TAB_NAMES = ("create", "compare", "views", "keys", "export")
COLUMNS = ("key", "number", "c1", "c2", "c3", "status", "state")
SHOW = ((u"all", u"All sheets"), (u"todo", u"To do (ticked)"), (u"problem", u"Problems"),
        (u"done", u"Up to date"))


def window_xaml():
    with open(XAML_FILE, "rb") as f:
        return f.read().decode("utf-8")


def matches(r, search):
    if not search:
        return True
    search = search.lower()
    return any(search in (r.get(k) or u"").lower() for k in ("number", "c1", "c2", "c3", "status"))


def show_filter(r, show):
    if show == u"todo":
        return r["do"]
    if show == u"problem":
        return r["state"] in (studio.BAD, studio.WARN) and not r["do"]
    if show == u"done":
        return r["state"] == studio.OK
    return True


class StudioWindow(object):
    """Plain controller around the XamlReader window.

    revit: dict of callbacks from lod.command:
      settings -> dict, save_settings(dict)
      pick_lod(current) -> path or None
      read_lod(path) -> (table, error text)
      sheets() -> [compare.Sheet]           with revision / area
      sheet_rows() -> [(id, number, name)]
      view_rows() -> [(id, name, set(sheet ids), legend)]
      keyplan_now(parameters) -> {sheet id: {parameter: value}}
      title_blocks() -> {'Family : Type': type id}
      create(items, title block id, keyplan fn) -> (made, failed, notes)
      apply(changes) -> [(change, why)]
      place([(sheet id, view id)]) -> (placed, [(sheet id, why)])
      keyplans([sheet id], keyplan fn) -> (done, [(sheet id, parameter, why)])
      sheet_parameters() -> [(parameter, kind, value)] or None
      edit_rules(values) -> True when the rules were changed
      save_file(default name) -> path or None
      project -> project name
    """

    def __init__(self, revit, model_text=u""):
        self.revit = revit
        self.values = revit["settings"]()
        self.table = None
        self.result = None
        self.sheets, self.sheet_list, self.views = [], [], []
        self.rows = {"create": [], "compare": [], "views": [], "keys": [], "export": []}
        self.notes = {}                 # row key -> (status, state) after an action
        self.win = ui.load_window(window_xaml(), ACCENT)
        for name in NAMES:
            setattr(self, name, self.win.FindName(name))
        self.ModelText.Text = model_text
        self.grids = {"create": self.CreateGrid, "compare": self.CompareGrid,
                      "views": self.ViewsGrid, "keys": self.KeyGrid, "export": self.ExportGrid}
        self.tables = {}
        for combo in (self.ViewsShowCombo, self.KeyShowCombo):
            for _, text in SHOW:
                combo.Items.Add(text)
            combo.SelectedIndex = 0
        self.blocks = revit["title_blocks"]()
        for name in sorted(self.blocks):
            self.TitleBlockCombo.Items.Add(name)
        if self.values.get("title_block") in self.blocks:
            self.TitleBlockCombo.SelectedItem = self.values["title_block"]
        elif self.blocks:
            self.TitleBlockCombo.SelectedIndex = 0
        self._fill_setup()
        self._wire()
        self._status(u"Reading the LOD and the sheets...", "")
        self.win.ContentRendered += self._first_load

    def _first_load(self, sender, args):
        if getattr(self, "_loaded", False):
            return
        self._loaded = True
        self.reload()

    # ------------------------------------------------------------ wiring

    def _wire(self):
        self.CloseButton.Click += lambda s, e: self.win.Close()
        self.BrowseButton.Click += self.on_browse
        self.ReloadButton.Click += lambda s, e: self.reload()
        self.SearchText.TextChanged += lambda s, e: self._fill_all()
        self.ViewsShowCombo.SelectionChanged += lambda s, e: self._fill("views")
        self.KeyShowCombo.SelectionChanged += lambda s, e: self._fill("keys")
        self.ExportUpdate.Checked += lambda s, e: self._fill_export()
        self.ExportNew.Checked += lambda s, e: self._fill_export()
        self.CreateButton.Click += self.on_create
        self.SyncButton.Click += self.on_sync
        self.PlaceButton.Click += self.on_place
        self.KeyButton.Click += self.on_keys
        self.ExportButton.Click += self.on_export
        self.SetupButton.Click += lambda s, e: self._setup(True)
        self.SetupDone.Click += lambda s, e: self._setup(False)
        self.RulesButton.Click += self.on_rules
        self.RulesResetButton.Click += self.on_rules_reset
        self.ParamsButton.Click += self.on_params
        for grid in self.grids.values():
            grid.PreviewKeyDown += self.on_key
        self.TickSelectedButton.Click += lambda s, e: self._tick(True, selected=True)
        self.UntickSelectedButton.Click += lambda s, e: self._tick(False, selected=True)
        self.TickAllButton.Click += lambda s, e: self._tick(True, selected=False)
        self.UntickAllButton.Click += lambda s, e: self._tick(False, selected=False)

    def _status(self, text, state):
        self.StatusText.Text = text
        fg, _ = ui.state_brushes(self.win, state)
        self.StatusDot.Fill = fg
        ui.pump(self.win)

    def _alert(self, text):
        from System.Windows import MessageBox
        MessageBox.Show(self.win, text, TITLE)

    def _ask(self, text):
        from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
        return MessageBox.Show(self.win, text, TITLE, MessageBoxButton.YesNo) == MessageBoxResult.Yes

    # ------------------------------------------------------------ setup

    def _fill_setup(self):
        self.PrefixText.Text = self.values.get("title_prefix") or u""
        self.RevText.Text = self.values.get("rev_param") or u""
        self.AreaText.Text = self.values.get("area_param") or u""
        custom = (self.values.get("keyplan_rules") or u"").strip()
        try:
            count = len(keyplan.parse_rules(self.values.get("keyplan_rules")))
            self.RulesInfo.Text = u"%d rules (%s)." % (count, u"your own" if custom else u"the defaults")
        except keyplan.RuleError as error:
            self.RulesInfo.Text = u"%s" % error

    def _setup(self, show):
        from System.Windows import Visibility
        if show:
            self._fill_setup()
            self.SetupPanel.Visibility = Visibility.Visible
            return
        changed = False
        for key, box, strip in (("title_prefix", self.PrefixText, False),
                                ("rev_param", self.RevText, True),
                                ("area_param", self.AreaText, True)):
            text = box.Text or u""
            text = text.strip() if strip else text
            if text != (self.values.get(key) or u""):
                self.values[key] = text
                changed = True
        self.SetupPanel.Visibility = Visibility.Collapsed
        if changed:
            self.revit["save_settings"](self.values)
            self.reload(read_lod=False)

    def on_rules(self, sender, args):
        if self.revit["edit_rules"](self.values):
            self._fill_setup()
            self._fill_keys()

    def on_rules_reset(self, sender, args):
        if not (self.values.get("keyplan_rules") or u"").strip():
            return
        if self._ask(u"Use the default key plan rules again (your own rules are dropped)?"):
            self.values["keyplan_rules"] = u""
            self.revit["save_settings"](self.values)
            self._fill_setup()
            self._fill_keys()

    def on_params(self, sender, args):
        found = self.revit["sheet_parameters"]()
        if found is None:
            self._alert(u"Open a sheet in Revit first (close this window, open the sheet, "
                        u"then open LOD Studio again).")
            return
        self._show("params", self.ParamsGrid,
                   [studio.row(i, u"", p, k, v) for i, (p, k, v) in enumerate(found)])

    # ------------------------------------------------------------ loading

    def on_browse(self, sender, args):
        path = self.revit["pick_lod"](self.values.get("lod_path") or u"")
        if path:
            self.values["lod_path"] = path
            self.revit["save_settings"](self.values)
            self.reload()

    def reload(self, read_lod=True):
        """Read the LOD (when asked) and the model, and fill every tab."""
        self.notes = {}
        path = self.values.get("lod_path") or u""
        self.FileText.Text = path or u"(pick the List of Deliverables with Browse...)"
        if read_lod:
            self.table = None
            if path and os.path.isfile(path):
                self._status(u"Reading %s with Excel..." % os.path.basename(path), "")
                self.table, error = self.revit["read_lod"](path)
                if error:
                    self._alert(error)
        self._status(u"Reading the sheets and views...", "")
        self._refresh_model()
        if self.table is None:
            self._status(u"Pick the LOD with Browse... to compare and create sheets. "
                         u"Views and key plans work without it.", "warn")
        else:
            self._status(u"LOD sheet '%s': %d drawings." % (self.table.sheet_name,
                                                           len(self.table.by_number())), "ok")

    def _refresh_model(self):
        self.sheets = self.revit["sheets"]()
        self.sheet_list = self.revit["sheet_rows"]()
        self.views = self.revit["view_rows"]()
        self._fill_lod()
        self._fill_views()
        self._fill_keys()
        self._fill_export()

    def _fill_lod(self):
        prefix = self.values.get("title_prefix") or u""
        if self.table is None:
            self.result = None
            self.rows["create"], self.rows["compare"] = [], []
            for kpi in (self.KpiDrawings, self.KpiMatched, self.KpiChanges, self.KpiMissing,
                        self.KpiExtra):
                kpi.Text = u"-"
        else:
            self.result = compare(self.table, self.sheets, prefix,
                                  use_rev=bool(self.values.get("rev_param")),
                                  use_area=bool(self.values.get("area_param")))
            self.rows["create"] = studio.create_rows(self.table, self.sheets, prefix)
            self.rows["compare"] = studio.compare_rows(self.result)
            counts = studio.compare_counts(self.result, self.table)
            self.KpiDrawings.Text = u"%d" % counts["drawings"]
            self.KpiMatched.Text = u"%d" % counts["matched"]
            self.KpiChanges.Text = u"%d" % counts["changes"]
            self.KpiMissing.Text = u"%d" % counts["missing"]
            self.KpiExtra.Text = u"%d" % counts["extra"]
        self._fill("create")
        self._fill("compare")

    def _fill_views(self):
        numbers = dict((i, n) for i, n, _ in self.sheet_list)
        self.rows["views"] = studio.view_rows(self.sheet_list, self.views, numbers,
                                              self.values.get("title_prefix") or u"")
        self._fill("views")

    def _rules(self):
        try:
            return keyplan.parse_rules(self.values.get("keyplan_rules"))
        except keyplan.RuleError as error:
            self._alert(u"%s\n\nFix them in Setup > Key plan rules." % error)
            return None

    def _fill_keys(self):
        rules = self._rules()
        if rules is None:
            self.rows["keys"] = []
        else:
            now = self.revit["keyplan_now"]([r["parameter"] for r in rules])
            self.rows["keys"] = studio.keyplan_rows(self.sheet_list, rules, now)
        self._fill("keys")

    def _fill_export(self):
        from_lod = bool(self.ExportUpdate.IsChecked) and self.table is not None
        counts = export.summary(self.sheets, self.table if from_lod else None,
                                self.values.get("title_prefix") or u"")
        self.rows["export"] = [studio.row(s or u"same", u"%d" % n, s or u"Unchanged")
                               for s, n in sorted(counts.items())]
        self._fill("export")

    # ------------------------------------------------------------ grids

    def _fill_all(self):
        for name in self.grids:
            self._fill(name)

    def _fill(self, name):
        rows = self.rows[name]
        search = (self.SearchText.Text or u"").strip()
        show = None
        if name == "views":
            show = SHOW[max(self.ViewsShowCombo.SelectedIndex, 0)][0]
        elif name == "keys":
            show = SHOW[max(self.KeyShowCombo.SelectedIndex, 0)][0]
        shown = [r for r in rows if matches(r, search) and (show is None or show_filter(r, show))]
        self._show(name, self.grids[name], shown)
        self._tab_counts()

    def _show(self, name, grid, rows):
        from System import Boolean, String
        from System.Data import DataTable
        table = DataTable(name)
        for col in COLUMNS:
            table.Columns.Add(col, String).DefaultValue = u""
        table.Columns.Add("do", Boolean).DefaultValue = False
        table.Columns.Add("can", Boolean).DefaultValue = False
        for r in rows:
            row = table.NewRow()
            status, state = self.notes.get(r["key"], (r["status"], r["state"]))
            for col in COLUMNS:
                row[col] = r.get(col) or u""
            row["status"], row["state"] = status, state
            row["do"], row["can"] = bool(r["do"]), bool(r["can"])
            table.Rows.Add(row)
        table.ColumnChanged += lambda s, e: self._ticked(name, e)
        self.tables[name] = table
        grid.ItemsSource = table.DefaultView

    def _ticked(self, name, args):
        if args.Column.ColumnName != "do":
            return
        value = bool(args.Row["do"])
        key = args.Row["key"]
        for r in self.rows.get(name, []):
            if r["key"] == key:
                r["do"] = value
        # a tick box clicked on one of several selected rows ticks them all
        if not getattr(self, "_spreading", False):
            rows = self._selected_rows(self.grids[name])
            if len(rows) > 1 and any(r["key"] == key for r in rows):
                self._set_rows(rows, value)
        self._tab_counts()

    @staticmethod
    def _selected_rows(grid):
        return [item.Row for item in grid.SelectedItems if hasattr(item, "Row")]

    def _set_rows(self, rows, value):
        self._spreading = True
        try:
            for r in rows:
                if bool(r["can"]) and bool(r["do"]) != value:
                    r["do"] = value
        finally:
            self._spreading = False

    def _tick(self, value, selected):
        """Tick or untick the selected rows, or every row shown, of this tab."""
        name = TAB_NAMES[max(self.Steps.SelectedIndex, 0)]
        table = self.tables.get(name)
        if table is None:
            return
        if selected:
            rows = self._selected_rows(self.grids[name])
            if not rows:
                self._status(u"Select rows first (click, then Shift or Ctrl + click).", "warn")
                return
        else:
            rows = list(table.Rows)
        self._set_rows(rows, value)
        self._tab_counts()

    def on_key(self, sender, args):
        """Space ticks or unticks the selected rows."""
        from System.Windows.Input import Key
        if args.Key != Key.Space:
            return
        rows = [r for r in self._selected_rows(sender) if bool(r["can"])]
        if rows:
            self._set_rows(rows, not all(bool(r["do"]) for r in rows))
            self._tab_counts()
            args.Handled = True

    def _tab_counts(self):
        def todo(name):
            return sum(1 for r in self.rows[name] if r["do"] and r["can"])
        self.CreateTabText.Text = u"Create sheets (%d)" % todo("create")
        self.CompareTabText.Text = u"Compare + sync (%d)" % todo("compare")
        self.ViewsTabText.Text = u"Place views (%d)" % todo("views")
        self.KeyTabText.Text = u"Key plans (%d)" % todo("keys")

    def _note(self, key, status, state):
        self.notes[u"%s" % key] = (status, state)

    # ------------------------------------------------------------ actions

    def on_create(self, sender, args):
        keys = set(studio.picked(self.rows["create"]))
        if not keys:
            self._alert(u"Tick the drawings to create sheets for.")
            return
        name = self.TitleBlockCombo.SelectedItem
        if not name:
            self._alert(u"Load a title block family first.")
            return
        if name != self.values.get("title_block"):
            self.values["title_block"] = name
            self.revit["save_settings"](self.values)
        rules = None
        if self.CreateKeyplans.IsChecked:
            rules = self._rules()
            if rules is None:
                return
        prefix = self.values.get("title_prefix") or u""
        from lod.table import sheet_name
        items, seen = [], set()
        for d in self.table.drawings:
            if d.number in keys and d.number not in seen:
                seen.add(d.number)
                items.append((d.number, sheet_name(d.title, prefix), d.rev, d.area))
        self._status(u"Creating %d sheets..." % len(items), "")
        fn = (lambda n: keyplan.values(n, rules)) if rules else None
        made, failed, notes = self.revit["create"](items, self.blocks[name], fn)
        placed = 0
        if self.CreateViews.IsChecked and made:
            self._refresh_model()
            new = set(n for n, _ in made)
            pairs = []
            for r in self.rows["views"]:
                if r["number"] in new and r["can"] and r["do"]:
                    sid, vid = r["key"].split(u":")
                    pairs.append((int(sid), int(vid)))
            if pairs:
                placed = len(self.revit["place"](pairs)[0])
        self.reload(read_lod=False)
        for number, why in failed:
            self._note(number, u"Not created: %s" % why, studio.BAD)
        text = u"%d sheets created" % len(made)
        if self.CreateViews.IsChecked:
            text += u", %d views placed" % placed
        if failed:
            text += u", %d failed (red rows)" % len(failed)
        if notes:
            text += u"; %d parameters not set (see Key plans)" % len(notes)
        self._fill("create")
        self._status(text + u".", "bad" if failed else "ok")

    def on_sync(self, sender, args):
        keys = studio.picked(self.rows["compare"])
        changes = studio.tidy_changes(self.result, keys) if self.result else []
        if not changes:
            self._alert(u"Tick the differences to write to the sheets.")
            return
        self._status(u"Writing %d changes..." % len(changes), "")
        failed = self.revit["apply"](changes)
        self.reload(read_lod=False)
        for c, why in failed:
            self._note(studio.change_key(c), u"Not changed: %s" % why, studio.BAD)
        self._fill("compare")
        self._status(u"%d changes written%s." % (
            len(changes) - len(failed), u", %d failed (red rows)" % len(failed) if failed else u""),
            "bad" if failed else "ok")

    def on_place(self, sender, args):
        pairs = []
        for key in studio.picked(self.rows["views"]):
            sid, vid = key.split(u":")
            pairs.append((int(sid), int(vid)))
        if not pairs:
            self._alert(u"Tick the sheets to place views on.")
            return
        self._status(u"Placing %d views..." % len(pairs), "")
        placed, failed = self.revit["place"](pairs)
        self.reload(read_lod=False)
        for sid, why in failed:
            for r in self.rows["views"]:
                if r["key"].startswith(u"%s:" % sid):
                    self._note(r["key"], u"Not placed: %s" % why, studio.BAD)
        self._fill("views")
        self._status(u"%d views placed%s." % (
            len(placed), u", %d failed (red rows)" % len(failed) if failed else u""),
            "bad" if failed else "ok")

    def on_keys(self, sender, args):
        ids = [int(k) for k in studio.picked(self.rows["keys"])]
        if not ids:
            self._alert(u"Tick the sheets to set the key plan of.")
            return
        rules = self._rules()
        if rules is None:
            return
        self._status(u"Setting %d key plans..." % len(ids), "")
        done, problems = self.revit["keyplans"](ids, lambda n: keyplan.values(n, rules))
        self._fill_keys()
        grouped = {}
        for sid, param, why in problems:
            grouped.setdefault(sid, []).append(param)
        for sid, params in grouped.items():
            self._note(sid, u"Not set: %s" % u", ".join(params), studio.BAD)
        self._fill("keys")
        self._status(u"Key plans set on %d sheets%s." % (
            done, u"; %d sheets miss parameters (red rows)" % len(grouped) if grouped else u""),
            "warn" if grouped else "ok")

    def on_export(self, sender, args):
        from_lod = bool(self.ExportUpdate.IsChecked)
        if from_lod and self.table is None:
            self._alert(u"Pick the LOD with Browse... first, or choose a new LOD from the sheets.")
            return
        if not [s for s in self.sheets if not s.placeholder]:
            self._alert(u"This model has no sheets.")
            return
        project = self.revit.get("project") or u""
        default = u"%s Electrical LOD.xlsx" % project if project else u"Electrical LOD.xlsx"
        path = self.revit["save_file"](default)
        if not path:
            return
        lod = self.values.get("lod_path") or u""
        if lod and os.path.normcase(path) == os.path.normcase(lod):
            self._alert(u"Save the export as a new file, not over the LOD it was made from.")
            return
        prefix = self.values.get("title_prefix") or u""
        book = export.workbook(self.sheets, self.table if from_lod else None, prefix, project)
        try:
            book.save(path)
        except Exception as error:
            self._alert(u"Could not save %s:\n%s\n\nIs it open in Excel?" % (path, error))
            return
        self._status(u"LOD saved: %s" % path, "ok")
        if self._ask(u"LOD saved. Open it now?"):
            os.startfile(path)

    def show(self):
        self.win.ShowDialog()
