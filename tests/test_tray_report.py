# -*- coding: utf-8 -*-
from traycoord import report, settings
from traycoord.route import box_obstacle, linear_obstacles, route

Z = 3.0


def _routed():
    pipe = linear_obstacles("p1", "Pipes : Standard", (5, -5, Z), (5, 5, Z),
                            [(4.95, -5, Z - 0.05), (5.05, 5, Z + 0.05)])
    wall = box_obstacle("w1", "Walls : 200", [(7.9, -5, 0.0), (8.1, 5, 4.0)], wall=True)
    result = route((0.0, 0.0, Z), (10.0, 0.0, Z), 0.3, 0.1, pipe + [wall],
                   limits=(2.4, 3.6))
    return [report.Routed(result, "t1", 0.3, 0.1, 0.05)]


def test_headline():
    assert report.headline(_routed(), "Drew") == \
        "Drew 1 tray run: 1 clash dodged, 1 wall opening to make."


def test_rows():
    routed = _routed()
    link = lambda key: "[%s]" % key
    assert report.dodge_rows(routed, link) == \
        [["[t1]", "over", "150 mm", "Pipes : Standard", "300 mm"]]
    (row,) = report.crossing_rows(routed, link)
    assert row[:3] == ["[w1]", "[t1]", "400 mm x 200 mm"]
    assert report.unsolved_rows(routed, link) == []


def test_settings_values():
    assert settings.valid("clearance", "75") == 75.0
    assert settings.valid("clearance", "-1") is None
    assert settings.valid("bends", "45") == "45"
    assert settings.valid("bends", "30") is None
    assert settings.valid("obstacles", "walls,nonsense,pipes") == "pipes,walls"
    assert settings.coerce("prefer", "sideways") == "shortest"


def test_settings_categories_and_options():
    values = dict(settings.DEFAULTS, obstacles="pipes,walls", bends="45", clearance=25.0)
    assert "OST_PipeCurves" in settings.categories(values)
    assert "OST_Walls" in settings.categories(values)
    assert "OST_DuctCurves" not in settings.categories(values)
    assert settings.options(values) == {"clearance": 0.025, "bends": 45, "prefer": "shortest"}
