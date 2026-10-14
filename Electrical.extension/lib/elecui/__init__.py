# -*- coding: utf-8 -*-
"""elecui: the shared look of the Electrical tab's windows (WPF).

Every tool window is plain XAML with a `<!--THEME-->` line inside its
`<Window.Resources>`: window_xaml() puts the shared styles (theme.xaml) there,
in the tool's colour, so XamlReader can load it under IronPython 2.7 and
CPython 3 alike. The frame is the same everywhere: a dark header band with
the tool's colour, step tabs, cards, green / amber / red status chips and a
footer with the main button.
"""
from __future__ import division

import os

HERE = os.path.dirname(os.path.abspath(__file__))
THEME_FILE = os.path.join(HERE, "theme.xaml")
MARKER = "<!--THEME-->"

# the colour of each tool
ACCENTS = {
    "power": "#E39B12",       # LV schematic and voltage drop
    "fire": "#D4483F",        # fire alarm
    "circuits": "#1A9A8A",    # typical floors
}


def soft(colour, amount=0.16):
    """`colour` mixed into white: the light tint behind selected rows."""
    colour = colour.lstrip("#")[-6:]
    rgb = [int(colour[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [int(round(255 + (c - 255) * amount)) for c in rgb]
    return "#FF%02X%02X%02X" % tuple(mixed)


def argb(colour):
    colour = colour.lstrip("#")
    return "#" + (colour if len(colour) == 8 else "FF" + colour).upper()


def theme_resources(accent):
    """The entries of theme.xaml, in the colour `accent` (a key of ACCENTS
    or a #RRGGBB colour)."""
    colour = ACCENTS.get(accent, accent)
    with open(THEME_FILE, "rb") as f:
        text = f.read().decode("utf-8")
    start = text.index(">", text.index("<ResourceDictionary")) + 1
    end = text.rindex("</ResourceDictionary>")
    body = text[start:end]
    body = body.replace("__ACCENT_SOFT__", soft(colour)).replace("__ACCENT__", argb(colour))
    return body


def window_xaml(text, accent):
    """`text` (a Window's XAML) with the theme in place of its marker."""
    if MARKER not in text:
        raise ValueError("the window XAML has no %s line" % MARKER)
    return text.replace(MARKER, theme_resources(accent), 1)


def load_references():
    import clr
    for name in ("PresentationFramework", "PresentationCore", "WindowsBase",
                 "System.Xaml", "System.Data", "System.Data.Common"):
        try:
            clr.AddReference(name)
        except Exception:
            pass


def load_window(text, accent):
    """Parse the window XAML (with the theme) and give it Revit as owner."""
    load_references()
    from System.Windows.Markup import XamlReader
    win = XamlReader.Parse(window_xaml(text, accent))
    set_owner(win)
    return win


def set_owner(win):
    try:
        from pyrevit import HOST_APP
        from System.Windows.Interop import WindowInteropHelper
        WindowInteropHelper(win).Owner = HOST_APP.proc_window
    except Exception:
        pass


def brush(win, key):
    """A brush of the theme (OkBrush, WarnBrush, BadBrush, AccentBrush...)."""
    return win.FindResource(key)


STATE_BRUSHES = {"ok": ("OkBrush", "OkBgBrush"), "warn": ("WarnBrush", "WarnBgBrush"),
                 "bad": ("BadBrush", "BadBgBrush"), "": ("NoneBrush", "BarBrush")}


def state_brushes(win, state):
    """(text brush, background brush) of a status: ok, warn, bad or ''."""
    fg, bg = STATE_BRUSHES.get(state or "", STATE_BRUSHES[""])
    return win.FindResource(fg), win.FindResource(bg)


def pump(win):
    """Let the window repaint (a status line) before a long step runs."""
    try:
        from System import Action
        from System.Windows.Threading import DispatcherPriority
        win.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.Background)
    except Exception:
        pass


def strings(values):
    """A .NET List[String], for ItemsSource."""
    from System import String
    from System.Collections.Generic import List
    out = List[String]()
    for v in values:
        out.Add(u"%s" % v)
    return out

