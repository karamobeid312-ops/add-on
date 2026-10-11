# -*- coding: utf-8 -*-
"""The CAD Lights window (WPF): one row per CAD block, with the lighting
fixture type to place on it.

Works with pyRevit's IronPython 2.7 and CPython 3 engines: the XAML is
loaded with XamlReader and the rows are added in code (no bindings)."""
from __future__ import division

from cadlights.match import SKIP

TITLE = "CAD Lights"

XAML = u"""<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="CAD Lights" Width="760" Height="560" MinWidth="560" MinHeight="320"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False" FontSize="12">
  <DockPanel Margin="10">
    <TextBlock x:Name="Intro" DockPanel.Dock="Top" TextWrapping="Wrap" Margin="0,0,0,8"/>
    <DockPanel DockPanel.Dock="Top" Margin="0,0,0,6">
      <TextBlock Text="Search:" VerticalAlignment="Center" Margin="0,0,6,0"/>
      <CheckBox x:Name="CheckedOnly" DockPanel.Dock="Right" Content="Show ticked only"
                VerticalAlignment="Center" Margin="10,0,0,0"/>
      <Button x:Name="UntickAll" DockPanel.Dock="Right" Content="Untick all" Width="80"
              Margin="6,0,0,0"/>
      <Button x:Name="TickShown" DockPanel.Dock="Right" Content="Tick shown" Width="80"
              Margin="6,0,0,0"/>
      <TextBox x:Name="SearchBox" VerticalContentAlignment="Center"/>
    </DockPanel>
    <DockPanel DockPanel.Dock="Bottom" Margin="0,10,0,0">
      <StackPanel DockPanel.Dock="Right" Orientation="Horizontal">
        <Button x:Name="CancelButton" Content="Cancel" Width="90" Margin="4,0"/>
        <Button x:Name="PlaceButton" Content="Place lights" Width="110" Margin="4,0"
                FontWeight="Bold" IsDefault="True"/>
      </StackPanel>
      <StackPanel Orientation="Vertical">
        <StackPanel Orientation="Horizontal" Margin="0,0,0,4">
          <TextBlock Text="Height of unhosted (level-based) lights above the level (mm):"
                     Width="380" VerticalAlignment="Center"/>
          <TextBox x:Name="HeightBox" Width="70"/>
        </StackPanel>
        <StackPanel Orientation="Horizontal">
          <TextBlock Text="Skip a spot that already has a light within (mm):"
                     Width="380" VerticalAlignment="Center"/>
          <TextBox x:Name="ToleranceBox" Width="70"/>
        </StackPanel>
      </StackPanel>
    </DockPanel>
    <Border BorderBrush="#FFBBBBBB" BorderThickness="1">
      <ScrollViewer VerticalScrollBarVisibility="Auto">
        <StackPanel x:Name="Rows" Margin="6"/>
      </ScrollViewer>
    </Border>
  </DockPanel>
</Window>
"""


def _number(text):
    try:
        value = float((u"%s" % text).strip())
    except ValueError:
        return None
    return value if value >= 0 else None


class MappingWindow(object):
    """rows: [(block name, count, [layers])]; types: ['Family : Type'];
    chosen: {block name: label} preselected. After show(): self.result is
    {block name: label or SKIP}, or None when cancelled."""

    def __init__(self, cad_name, level_name, rows, types, chosen, height_mm, tolerance_mm):
        import clr
        for name in ("PresentationFramework", "PresentationCore", "WindowsBase", "System.Xaml"):
            try:
                clr.AddReference(name)
            except Exception:
                pass
        from System.Windows.Markup import XamlReader
        self.win = XamlReader.Parse(XAML)
        self.rows = rows
        self.types = [SKIP] + list(types)
        self.combos = {}
        self.result = None
        self.height_mm = height_mm
        self.tolerance_mm = tolerance_mm
        f = self.win.FindName
        self.Rows, self.HeightBox, self.ToleranceBox = f("Rows"), f("HeightBox"), f("ToleranceBox")
        f("Intro").Text = (
            u"%d block names found in %s. Tick the light blocks (search to find them) and "
            u"pick the lighting fixture type for each. Unticked blocks are skipped. Lights go "
            u"on the ceiling above, on level %s." % (len(rows), cad_name, level_name))
        self.SearchBox, self.CheckedOnly = f("SearchBox"), f("CheckedOnly")
        self.checks = {}
        self.grids = {}
        self.HeightBox.Text = u"%g" % height_mm
        self.ToleranceBox.Text = u"%g" % tolerance_mm
        for name, count, layers in rows:
            self._add_row(name, count, layers, chosen.get(name, SKIP))
        self.SearchBox.TextChanged += self.on_filter
        self.CheckedOnly.Click += self.on_filter
        f("TickShown").Click += self.on_tick_shown
        f("UntickAll").Click += self.on_untick_all
        f("PlaceButton").Click += self.on_place
        f("CancelButton").Click += self.on_cancel
        self._set_owner()

    def _set_owner(self):
        try:
            from pyrevit import HOST_APP
            from System.Windows.Interop import WindowInteropHelper
            WindowInteropHelper(self.win).Owner = HOST_APP.proc_window
        except Exception:
            pass

    def _add_row(self, name, count, layers, selected):
        from System.Windows import GridLength, GridUnitType, Thickness, VerticalAlignment
        from System.Windows.Controls import CheckBox, ColumnDefinition, ComboBox, Grid
        grid = Grid()
        grid.Margin = Thickness(0, 2, 0, 2)
        for width in (GridLength(1, GridUnitType.Star), GridLength(320)):
            column = ColumnDefinition()
            column.Width = width
            grid.ColumnDefinitions.Add(column)
        check = CheckBox()
        text = u"%s  \u00d7 %d" % (name, count)
        if layers:
            check.ToolTip = u"Layer: " + u", ".join(layers)
            text += u"   (%s)" % u", ".join(layers[:2])
        check.Content = text
        check.VerticalAlignment = VerticalAlignment.Center
        check.IsChecked = selected in self.types and selected != SKIP
        combo = ComboBox()
        for item in self.types:
            combo.Items.Add(item)
        combo.SelectedIndex = self.types.index(selected) if selected in self.types else 0
        combo.IsEnabled = bool(check.IsChecked)
        check.Click += lambda sender, args: self._ticked(name)
        Grid.SetColumn(combo, 1)
        grid.Children.Add(check)
        grid.Children.Add(combo)
        self.Rows.Children.Add(grid)
        self.combos[name] = combo
        self.checks[name] = check
        self.grids[name] = grid

    def _ticked(self, name):
        self.combos[name].IsEnabled = bool(self.checks[name].IsChecked)
        if self.CheckedOnly.IsChecked:
            self.on_filter(None, None)

    def _shown(self, name):
        words = (u"%s" % (self.SearchBox.Text or u"")).lower().split()
        if self.CheckedOnly.IsChecked and not self.checks[name].IsChecked:
            return False
        return all(w in name.lower() for w in words)

    def on_filter(self, sender, args):
        from System.Windows import Visibility
        for name, grid in self.grids.items():
            grid.Visibility = Visibility.Visible if self._shown(name) else Visibility.Collapsed

    def on_tick_shown(self, sender, args):
        for name in self.grids:
            if self._shown(name):
                self.checks[name].IsChecked = True
                self.combos[name].IsEnabled = True

    def on_untick_all(self, sender, args):
        for name in self.grids:
            self.checks[name].IsChecked = False
            self.combos[name].IsEnabled = False
        self.on_filter(None, None)

    def on_place(self, sender, args):
        from pyrevit import forms
        height = _number(self.HeightBox.Text)
        tolerance = _number(self.ToleranceBox.Text)
        if height is None or tolerance is None:
            forms.alert("Enter the height and the distance in mm.", title=TITLE)
            return
        result = {}
        for name, combo in self.combos.items():
            if self.checks[name].IsChecked:
                result[name] = u"%s" % (combo.SelectedItem or SKIP)
            else:
                result[name] = SKIP
        if all(v == SKIP for v in result.values()):
            forms.alert("Tick at least one block and pick its fixture type.", title=TITLE)
            return
        self.height_mm, self.tolerance_mm = height, tolerance
        self.result = result
        self.win.Close()

    def on_cancel(self, sender, args):
        self.result = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.result
