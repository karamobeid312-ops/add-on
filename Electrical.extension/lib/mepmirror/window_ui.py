# -*- coding: utf-8 -*-
"""The Mirror Tower (Mechanical / Plumbing) window (WPF), in the Electrical
tab's shared look: a top bar (Tower 1's scope box, Tower 2, Setup), the
Floors and Results tabs, and a Setup pop-up.

Works with pyRevit's IronPython 2.7 and CPython 3 engines: the XAML is
loaded with XamlReader, events are wired here and the grids show a
System.Data.DataTable. The Revit side comes in as callbacks from
mepmirror.command. Clicking Tower 2's points needs Revit, so the window
closes for it (action "pick") and command.run opens it again with the
same state.
"""
from __future__ import division

import os

import elecui as ui
from mepmirror import plan, report, rules
from mirrortower import geometry

XAML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window.xaml")
NAMES = ("BadgeText", "TitleText", "SubText", "ModelText", "StatusDot", "StatusText",
         "CloseButton", "SetupButton", "BoxCombo", "PickButton", "Tower2Text", "Steps",
         "FloorsInfo", "TickAllButton", "TickNoneButton", "MirrorButton", "MirrorInfo",
         "FloorGrid", "ResultsTabText", "SelectRowButton", "SelectNewButton", "ResultsInfo",
         "ResultGrid", "SetupPanel", "SetupDone", "CategoryList", "CategoryInfo", "ModeCombo",
         "ToleranceText", "JoinCheck")
FLOOR_COLUMNS = ("key", "floor", "tower1", "already", "todo", "skipped", "status", "state")
RESULT_COLUMNS = ("key", "floor", "what", "count", "item", "status", "state")

BY_POINTS = "points"
LINE_HERE = "line"
LINE_LINK = "link"
MODES = ((BY_POINTS, u"Click 2 points in Tower 1, then the same 2 in Tower 2"),
         (LINE_HERE, u"Plain mirror about a grid or line in this model"),
         (LINE_LINK, u"Plain mirror about a grid or line in a linked model"))

TEXT = {
    rules.MECHANICAL: (u"Mirror Tower · Mechanical", u"MECH",
                       u"Tower 2's ducts, HVAC pipes, air terminals and equipment as the mirror "
                       u"of Tower 1's"),
    rules.PLUMBING: (u"Mirror Tower · Plumbing", u"PLMB",
                     u"Tower 2's water and drainage pipes, fixtures and sprinklers as the mirror "
                     u"of Tower 1's"),
}
ACCENTS = {rules.MECHANICAL: "#2F7FD8", rules.PLUMBING: "#3E9B4F"}


def window_xaml():
    with open(XAML_FILE, "rb") as f:
        return f.read().decode("utf-8")


def parse_mm(text, default):
    """A tolerance in mm typed by the user, kept between 1 and 1000."""
    try:
        value = float((text or u"").strip().replace(u",", u"."))
    except ValueError:
        return default
    return min(max(value, 1.0), 1000.0)


def sides_of(model, outline, placement, tolerance):
    """{floor key: plan.Side} of every floor with things, paired when
    Tower 2 is given."""
    sides = {}
    for key, _, _ in model.floors:
        things = model.things.get(key) or []
        if not things:
            continue
        if placement is None:
            side = plan.Side()
            for t in things:
                inside = [geometry.inside(outline, p[0], p[1], tolerance) for p in t.ends()]
                if all(inside) and t.grouped:
                    side.grouped.append(t)
                elif all(inside):
                    side.tower1.append(t)
                elif any(inside) and not t.grouped:
                    side.leaves.append(t)
            sides[key] = side
        else:
            sides[key] = plan.pair(plan.split(things, outline, placement, tolerance),
                                   placement, tolerance)
    return sides


class MirrorWindow(object):
    """Plain controller around the XamlReader window.

    revit: dict of callbacks and values from mepmirror.command:
      domain                rules.MECHANICAL or rules.PLUMBING
      boxes                 [scope box names]
      outline(name)         Tower 1's outline in plan [(x, y)]
      read(unticked)        revit_mep.Model of the tool's elements
      mirror(keys, sides, placement, about, tolerance, join) -> [FloorResult]
      label_of(key), key_of(element id), select(ids)
      keep(values)          remember the choices for next time
      model_text            the header's right side
    state: dict kept while the tool runs (the window opens again after
    Tower 2's points are clicked).
    """

    def __init__(self, revit, state):
        self.revit = revit
        self.state = state
        self.domain = revit["domain"]
        self.action = None
        self.sides = {}
        self.outline = []
        self.result_ids = {}
        self._quiet = False
        self.win = ui.load_window(window_xaml(), ACCENTS[self.domain])
        for name in NAMES:
            setattr(self, name, self.win.FindName(name))
        title, badge, sub = TEXT[self.domain]
        self.win.Title = title
        self.TitleText.Text = title
        self.BadgeText.Text = badge
        self.SubText.Text = sub
        self.ModelText.Text = revit.get("model_text") or u""
        self._fill_bar()
        self._fill_setup()
        self._wire()
        if state.get("results"):
            self._fill_results()
        self._status(u"Reading the model...", "")
        self.win.ContentRendered += self._first_load

    def _first_load(self, sender, args):
        if getattr(self, "_loaded", False):
            return
        self._loaded = True
        import time
        start = time.time()
        if self.state.get("model") is None:
            self.state["model"] = self.revit["read"](self.state["unticked"])
            self.state["read_with"] = set(self.state["unticked"])
        self.refresh()
        if self.state.get("tab"):
            self.Steps.SelectedIndex = self.state["tab"]
        if not self.state.get("opened"):
            self.state["opened"] = True
            self.ModelText.Text = self.ModelText.Text + u"\nOpened in %.1f s" % (
                time.time() - start + self.state.get("open_s", 0.0))

    # ------------------------------------------------------------ setup

    def _wire(self):
        self.CloseButton.Click += lambda s, e: self.win.Close()
        self.BoxCombo.SelectionChanged += self.on_box
        self.PickButton.Click += self.on_pick
        self.TickAllButton.Click += lambda s, e: self._tick(True)
        self.TickNoneButton.Click += lambda s, e: self._tick(False)
        self.MirrorButton.Click += self.on_mirror
        self.SelectRowButton.Click += self.on_select_row
        self.SelectNewButton.Click += lambda s, e: self._select(self.state.get("new_ids") or [])
        self.ResultGrid.MouseDoubleClick += self.on_select_row
        self.SetupButton.Click += lambda s, e: self._setup(True)
        self.SetupDone.Click += lambda s, e: self._setup(False)

    def _fill_bar(self):
        self._quiet = True
        try:
            boxes = self.revit["boxes"]
            for name in boxes:
                self.BoxCombo.Items.Add(name)
            if self.state.get("box") in boxes:
                self.BoxCombo.SelectedIndex = boxes.index(self.state["box"])
            elif boxes:
                self.BoxCombo.SelectedIndex = 0
                self.state["box"] = boxes[0]
        finally:
            self._quiet = False
        self._tower2_text()

    def _fill_setup(self):
        from System.Windows.Controls import CheckBox, ListBoxItem
        from System.Windows import Thickness
        for name, label in rules.CATEGORIES[self.domain]:
            if name not in self.revit.get("categories", [name]):
                continue
            box = CheckBox()
            box.Content = label
            box.Tag = name
            box.IsChecked = name not in self.state["unticked"]
            box.Margin = Thickness(0, 2, 0, 2)
            item = ListBoxItem()
            item.Content = box
            self.CategoryList.Items.Add(item)
        if self.domain == rules.MECHANICAL:
            self.CategoryInfo.Text = (u"Pipes are split by their system: chilled water, heating, "
                                      u"condensate and refrigerant are mechanical; water, "
                                      u"drainage and fire are the Plumbing tool's. Equipment is "
                                      u"mechanical unless all its pipes are plumbing (pumps, "
                                      u"water heaters).")
        else:
            self.CategoryInfo.Text = (u"Pipes are split by their system: water, drainage, vent "
                                      u"and fire are plumbing; chilled water, heating, condensate "
                                      u"and refrigerant are the Mechanical tool's. Equipment is "
                                      u"plumbing when all its pipes are plumbing (pumps, water "
                                      u"heaters).")
        for _, text in MODES:
            self.ModeCombo.Items.Add(text)
        modes = [m for m, _ in MODES]
        mode = self.state.get("mode")
        self.ModeCombo.SelectedIndex = modes.index(mode) if mode in modes else 0
        self.ToleranceText.Text = (u"%.1f" % self.state["tolerance_mm"]).rstrip(u"0").rstrip(u".")
        self.JoinCheck.IsChecked = bool(self.state.get("join", True))

    def _setup(self, show):
        from System.Windows import Visibility
        if show:
            self.SetupPanel.Visibility = Visibility.Visible
            return
        self.SetupPanel.Visibility = Visibility.Collapsed
        unticked = set()
        for item in self.CategoryList.Items:
            if not item.Content.IsChecked:
                unticked.add(u"%s" % item.Content.Tag)
        mode = MODES[max(self.ModeCombo.SelectedIndex, 0)][0]
        tolerance = parse_mm(self.ToleranceText.Text, self.state["tolerance_mm"])
        self.ToleranceText.Text = (u"%.1f" % tolerance).rstrip(u"0").rstrip(u".")
        if mode != self.state.get("mode"):
            self.state["placement"] = None      # given another way: pick again
            self.state["placement_text"] = u""
        self.state.update(unticked=unticked, mode=mode, tolerance_mm=tolerance,
                          join=bool(self.JoinCheck.IsChecked))
        self.revit["keep"]({"unticked": u"|".join(sorted(unticked)), "mode": mode,
                            "tolerance_mm": tolerance, "join": bool(self.JoinCheck.IsChecked)})
        self._tower2_text()
        if unticked != set(self.state["read_with"]):
            self._status(u"Reading the model...", "")
            self.state["model"] = self.revit["read"](unticked)
            self.state["read_with"] = set(unticked)
        self.refresh()

    # ------------------------------------------------------------ helpers

    def _status(self, text, state):
        self.StatusText.Text = text
        fg, _ = ui.state_brushes(self.win, state)
        self.StatusDot.Fill = fg
        ui.pump(self.win)

    def _alert(self, text):
        from System.Windows import MessageBox
        MessageBox.Show(self.win, text, self.win.Title)

    def _tolerance(self):
        return self.state["tolerance_mm"] / 304.8

    def _tower2_text(self):
        placement = self.state.get("placement")
        mode = self.state.get("mode") or BY_POINTS
        self.PickButton.Content = u"Pick Tower 2..." if mode == BY_POINTS else \
            u"Pick the mirror line..."
        if placement is None:
            self.Tower2Text.Text = u"not given yet: pick it"
        else:
            self.Tower2Text.Text = self.state.get("placement_text") or u"given"

    @staticmethod
    def _table(columns, items):
        """DataTable of [(values, write, can)]."""
        from System import Boolean, String
        from System.Data import DataTable
        table = DataTable("Rows")
        for name in columns:
            table.Columns.Add(name, String).DefaultValue = u""
        table.Columns.Add("write", Boolean).DefaultValue = False
        table.Columns.Add("can", Boolean).DefaultValue = False
        for values, write, can in items:
            row = table.NewRow()
            for name in columns:
                row[name] = String(values.get(name) or u"")
            row["write"] = write
            row["can"] = can
            table.Rows.Add(row)
        table.AcceptChanges()
        return table

    # ------------------------------------------------------------ floors

    def refresh(self):
        model = self.state.get("model")
        if model is None:
            return
        name = self.state.get("box")
        self.outline = self.revit["outline"](name) if name else []
        placement = self.state.get("placement")
        if len(self.outline) < 3:
            self.sides = {}
            self._fill_floors()
            self._status(u"Pick the scope box drawn around Tower 1." if not name else
                         u"Could not read the outline of scope box %s." % name, "bad")
            return
        if placement is not None and geometry.inside(
                self.outline, *placement.apply(*geometry.centre(self.outline))):
            self.Tower2Text.Text = u"puts Tower 2 on top of Tower 1: pick it again"
            placement = None
        self.sides = sides_of(model, self.outline, placement, self._tolerance())
        self._fill_floors()
        todo = sum(len(s.missing) for s in self.sides.values())
        if not self.sides:
            self._no_elements()
        elif placement is None:
            self._status(u"Pick Tower 2, then tick the floors to mirror.", "")
        elif todo:
            self._status(u"%d elements of Tower 1 to mirror. Tick the floors and press Mirror."
                         % todo, "ok")
        else:
            self._status(u"Tower 2 has all of Tower 1's %s elements." % self.domain, "ok")

    def _no_elements(self):
        """Say why the floors are empty: the ducts and pipes are usually in
        the mechanical / plumbing model linked here, and a link cannot be
        changed from this model."""
        try:
            links = self.revit["in_links"](self.state["unticked"])
        except Exception:
            links = []
        if not links:
            self._status(u"No %s elements in this model or its links." % self.domain, "warn")
            return
        names = u", ".join(u"%s (%d)" % (t, n) for t, n in links[:3])
        self._status(u"No %s elements in this model; they are in the link %s. Open that model "
                     u"and run Mirror Tower there." % (self.domain, names), "warn")
        self._alert(u"This model has no %s elements: they are in the linked model\n\n%s\n\n"
                    u"A tool can only change the model that is open, not a link. Open that "
                    u"model in Revit (with this extension) and run Mirror Tower there." % (
                        self.domain, u"\n".join(u"  %s: %d elements" % (t, n)
                                                for t, n in links)))

    def _fill_floors(self):
        model = self.state["model"]
        placement = self.state.get("placement")
        ticked = self.state.get("ticked")
        items = []
        for key, _, _ in reversed(model.floors):         # top floor first, like a section
            side = self.sides.get(key)
            if side is None:
                continue
            values, state = report.floor_row(model.names[key], side, placement is not None)
            values["key"] = u"%d" % key
            values["state"] = state
            can = placement is not None and bool(side.missing)
            write = can and (key in ticked if ticked is not None else True)
            items.append((values, write, can))
        table = self._table(FLOOR_COLUMNS, items)
        table.ColumnChanged += lambda s, e: self._mirror_info()
        self.FloorGrid.ItemsSource = table.DefaultView
        skipped_note = u" A run with one end out of the box (into a riser, the podium) is " \
                       u"skipped, not mirrored."
        other = model.other_side
        self.FloorsInfo.Text = (
            u"Tower 1 is everything in scope box %s; Tower 2 already having an element (same "
            u"type at the mirrored spot, within %s mm) is not mirrored again.%s%s" % (
                self.state.get("box") or u"?",
                (u"%.1f" % self.state["tolerance_mm"]).rstrip(u"0").rstrip(u"."), skipped_note,
                (u" %d pipes and pieces of equipment are the %s tool's." % (
                    other, u"Plumbing" if self.domain == rules.MECHANICAL else u"Mechanical"))
                if other else u""))
        self._mirror_info()

    def _ticked(self):
        keys = []
        view = self.FloorGrid.ItemsSource
        if view is None:
            return keys
        for row in view:
            if row["write"] and row["can"]:
                keys.append(int(u"%s" % row["key"]))
        return keys

    def _keep_ticks(self):
        view = self.FloorGrid.ItemsSource
        if view is None or self.state.get("placement") is None:
            return
        ticked = set(self.state.get("ticked") or ())
        for row in view:
            key = int(u"%s" % row["key"])
            if row["can"]:
                if row["write"]:
                    ticked.add(key)
                else:
                    ticked.discard(key)
        self.state["ticked"] = ticked

    def _mirror_info(self):
        if self.state.get("placement") is None:
            self.MirrorInfo.Text = u"Pick Tower 2 first (top bar)."
            return
        n = sum(len(self.sides[k].missing) for k in self._ticked() if k in self.sides)
        self.MirrorInfo.Text = u"Ticking only what you want: the rest stays as it is. " \
            u"One undo takes the whole run back." if not n else \
            u"%d elements on the ticked floors. One undo takes the whole run back." % n

    def _tick(self, value):
        view = self.FloorGrid.ItemsSource
        if view is None:
            return
        for row in view:
            if row["can"]:
                row["write"] = value
        self._keep_ticks()
        self._mirror_info()

    # ------------------------------------------------------------ actions

    def on_box(self, sender, args):
        if self._quiet or self.BoxCombo.SelectedItem is None:
            return
        self.state["box"] = u"%s" % self.BoxCombo.SelectedItem
        self.revit["keep"]({"box": self.state["box"]})
        self.refresh()

    def on_pick(self, sender, args):
        self._keep_ticks()
        self.state["tab"] = self.Steps.SelectedIndex
        self.action = "pick"
        self.win.Close()

    def on_mirror(self, sender, args):
        if self.state.get("placement") is None:
            self._alert(u"Pick Tower 2 first: the button in the top bar.")
            return
        self._keep_ticks()
        keys = [k for k in self._ticked() if self.sides.get(k) and self.sides[k].missing]
        if not keys:
            self._alert(u"Tick a floor with elements to mirror.")
            return
        self._status(u"Mirroring %d floor(s)..." % len(keys), "")
        try:
            results = self.revit["mirror"](keys, self.sides, self.state["placement"],
                                           geometry.centre(self.outline), self._tolerance(),
                                           bool(self.state.get("join", True)))
        except Exception as error:
            self._status(u"Revit stopped the run: nothing was changed.", "bad")
            self._alert(u"Revit stopped the run, nothing was changed:\n\n%s" % error)
            return
        rows = []
        new_ids = []
        for r in results:
            rows.extend(report.result_rows(r, self.revit["label_of"], self.revit["key_of"]))
            new_ids.extend(r.mirrored)
        self.state["results"] = rows
        self.state["new_ids"] = new_ids
        self._fill_results()
        self._status(u"Re-reading the model...", "")
        self.state["model"] = self.revit["read"](self.state["unticked"])
        self.state["read_with"] = set(self.state["unticked"])
        self.refresh()
        self.Steps.SelectedIndex = 1
        self._select(new_ids)
        bad = sum(1 for _, state, _ in rows if state == report.BAD)
        warn = sum(1 for _, state, _ in rows if state == report.WARN)
        self._status(u"%d elements mirrored into Tower 2 (selected in Revit)%s." % (
            len(new_ids), u"; %d rows to check in Results" % (bad + warn) if bad + warn else u""),
            "bad" if bad else ("warn" if warn else "ok"))

    def _fill_results(self):
        rows = self.state.get("results") or []
        items = []
        self.result_ids = {}
        for i, (values, state, ids) in enumerate(rows):
            values = dict(values)
            values["key"] = u"%d" % i
            values["status"] = values["what"]
            values["state"] = state
            self.result_ids[i] = ids
            items.append((values, False, False))
        self.ResultGrid.ItemsSource = self._table(RESULT_COLUMNS, items).DefaultView
        n = len(self.state.get("new_ids") or [])
        self.ResultsTabText.Text = u"Results (%d new)" % n if rows else u"Results"
        self.ResultsInfo.Text = u"Pick a row and select it in Revit (or double-click it). " \
                                u"Tower 1's elements are selected for rows that were not " \
                                u"mirrored."

    def on_select_row(self, sender, args):
        row = self.ResultGrid.SelectedItem
        if row is None:
            return
        ids = self.result_ids.get(int(u"%s" % row["key"])) or []
        if not ids:
            self._status(u"That row has no elements to select.", "")
            return
        self._select(ids)

    def _select(self, ids):
        if not ids:
            return
        n = self.revit["select"](ids)
        self._status(u"%d elements selected in Revit." % n, "ok")

    def show(self):
        self.win.ShowDialog()
        return self.action
