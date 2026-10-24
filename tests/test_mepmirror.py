# -*- coding: utf-8 -*-
from mirrortower.geometry import mirror_placement
from mepmirror import plan, rules
from mepmirror.plan import Thing

M, P, F = rules.MECHANICAL, rules.PLUMBING, rules.FIRE
BOX = [(0, 0), (10, 0), (10, 10), (0, 10)]      # Tower 1
LINE = mirror_placement((15, 0), (15, 1))        # Tower 2 is x -> 30 - x
TOL = 0.05 / 0.3048


# ---------------------------------------------------------------- rules

def test_hydronic_pipes_are_mechanical():
    assert rules.pipe_domain(u"Hydronic Supply") == M
    assert rules.pipe_domain(u"ReturnHydronic") == M


def test_water_and_drainage_are_plumbing():
    for kind in (u"Domestic Cold Water", u"Domestic Hot Water", u"Sanitary", u"Vent",
                 u"Other"):
        assert rules.pipe_domain(kind, [u"DCW"]) == P


def test_condensate_named_system_is_mechanical_even_as_sanitary():
    assert rules.pipe_domain(u"Sanitary", [u"Condensate Drain", u"CD"]) == M
    assert rules.pipe_domain(u"Other", [u"CHW Supply"]) == M
    assert rules.pipe_domain(u"Other", [u"Refrigerant_Liquid"]) == M


def test_unknown_system_is_none():
    assert rules.pipe_domain(u"", []) is None
    assert rules.pipe_domain(u"Undefined", []) is None


def test_equipment_side():
    assert rules.equipment_domain(2, [P]) == M              # an AHU with a drain
    assert rules.equipment_domain(0, [P, P]) == P            # a water pump
    assert rules.equipment_domain(0, [M, P]) == M            # an FCU
    assert rules.equipment_domain(0, []) == M


def test_settle_takes_neighbours_side_through_unknowns():
    domains = {1: M, 2: None, 3: None, 4: None}
    neighbours = {1: [2], 2: [1, 3], 3: [2]}
    out = rules.settle(domains, neighbours)
    assert out == {1: M, 2: M, 3: M, 4: P}


# ---------------------------------------------------------------- floors

def test_pick_floor_prefers_own_level_then_highest_bottom():
    floors = [(1, -1.0, 12.0), (2, 11.0, 24.0), (3, 23.0, None)]
    assert plan.pick_floor(Thing(9, 1, (0, 0, 11.5), level=1), floors) == 1
    assert plan.pick_floor(Thing(9, 1, (0, 0, 11.5)), floors) == 2
    assert plan.pick_floor(Thing(9, 1, (0, 0, 30.0), level=1), floors) == 3
    assert plan.pick_floor(Thing(9, 1, (0, 0, -5.0)), floors) is None
    # a vertical pipe is on the floor of its lower end
    assert plan.pick_floor(Thing(9, 1, (0, 0, 30.0), (0, 0, 5.0)), floors) == 1


# ---------------------------------------------------------------- split / pair

def _floor():
    return [
        Thing(1, 10, (2, 2, 9)),                         # terminal in Tower 1
        Thing(2, 20, (1, 1, 9), (8, 1, 9)),              # duct in Tower 1
        Thing(3, 20, (8, 5, 9), (12, 5, 9)),             # duct out to the podium
        Thing(4, 10, (28, 2, 9)),                        # Tower 2 has the terminal
        Thing(5, 20, (22, 1, 9), (29, 1, 9)),            # and the duct (drawn the other way)
        Thing(6, 10, (40, 40, 9)),                       # elsewhere
    ]


def test_split_by_box():
    side = plan.split(_floor(), BOX, LINE, TOL)
    assert sorted(t.key for t in side.tower1) == [1, 2]
    assert [t.key for t in side.leaves] == [3]
    assert sorted(t.key for t in side.pool) == [4, 5, 6]


def test_pair_finds_existing_copies_and_runs_drawn_backwards():
    side = plan.pair(plan.split(_floor(), BOX, LINE, TOL), LINE, TOL)
    assert side.copies == {1: 4, 2: 5}
    assert side.missing == []


def test_missing_when_type_differs_or_one_end_off():
    things = [Thing(1, 10, (2, 2, 9)), Thing(2, 20, (1, 1, 9), (8, 1, 9)),
              Thing(4, 11, (28, 2, 9)), Thing(5, 20, (29, 1, 9), (25, 1, 9))]
    side = plan.pair(plan.split(things, BOX, LINE, TOL), LINE, TOL)
    assert side.copies == {}
    assert sorted(t.key for t in side.missing) == [1, 2]


def test_point_matches_by_family_when_type_differs():
    things = [Thing(1, 10, (2, 2, 9), family_key=7), Thing(4, 11, (28, 2, 9), family_key=7)]
    side = plan.pair(plan.split(things, BOX, LINE, TOL), LINE, TOL)
    assert side.copies == {1: 4}


def test_height_must_match():
    things = [Thing(1, 10, (2, 2, 9)), Thing(4, 10, (28, 2, 12))]
    side = plan.pair(plan.split(things, BOX, LINE, TOL), LINE, TOL)
    assert side.copies == {}


def test_thing_on_the_mirror_line_is_shared():
    box = [(10, 0), (20, 0), (20, 10), (10, 10)]
    things = [Thing(1, 10, (15, 3, 9)), Thing(2, 20, (15, 1, 0), (15, 1, 30)),
              Thing(3, 10, (12, 3, 9))]
    side = plan.split(things, box, LINE, TOL)
    assert sorted(t.key for t in side.shared) == [1, 2]
    assert [t.key for t in side.tower1] == [3]


def test_landed():
    expected = [Thing(1, 10, (2, 2, 9)), Thing(2, 20, (1, 1, 9), (8, 1, 9))]
    made = [Thing(11, 10, (28, 2, 9)), Thing(12, 20, (2, 1, 9), (8, 1, 9))]   # 12 stayed
    assert plan.landed(expected, made, LINE, TOL) == {1: 11}


# ---------------------------------------------------------------- joints

def test_joints_pair_open_ends_of_different_elements():
    ends = [(1, 0, (0, 0, 0), "pipe"), (2, 0, (0.001, 0, 0), "pipe"),
            (3, 0, (0.002, 0, 0), "pipe"), (4, 0, (0, 0, 0), "duct"),
            (1, 1, (5, 5, 5), "pipe")]
    pairs = plan.joints(ends)
    assert len(pairs) == 1
    (a, b), = pairs
    assert set([a[0], b[0]]) == set([1, 2])


# ---------------------------------------------------------------- window rows

class _Result(object):
    def __init__(self, **kw):
        self.floor = u"L5"
        self.tower1 = self.already = self.shared = self.rehosted = self.joined = 0
        self.leaves, self.grouped, self.mirrored, self.off_spot = [], [], [], []
        self.no_wall, self.refused, self.errors = [], [], []
        self.__dict__.update(kw)


def test_floor_row_states():
    from mepmirror import report
    side = plan.pair(plan.split(_floor(), BOX, LINE, TOL), LINE, TOL)
    values, state = report.floor_row(u"L5", side, True)
    assert values["tower1"] == u"2" and values["already"] == u"2" and values["todo"] == u""
    assert values["skipped"] == u"1" and state == report.WARN
    things = [Thing(1, 10, (2, 2, 9))]
    side = plan.pair(plan.split(things, BOX, LINE, TOL), LINE, TOL)
    values, state = report.floor_row(u"L5", side, True)
    assert values["todo"] == u"1" and state == report.OK
    values, state = report.floor_row(u"L5", side, False)
    assert values["status"] == u"Pick Tower 2 first"


def test_result_rows_name_the_types():
    from mepmirror import report
    labels = {1: u"Pipe : CHW", 2: u"Pipe : CHW", 3: u"Duct : Rect"}
    r = _Result(mirrored=[1, 2, 3], leaves=[3], already=4, joined=2)
    rows = report.result_rows(r, labels.get, lambda i: i)
    whats = [v["what"] for v, _, _ in rows]
    assert whats[0] == u"Mirrored into Tower 2"
    assert rows[0][0]["item"] == u"Pipe : CHW (2), Duct : Rect (1)"
    assert u"Open ends joined" in whats and u"Already in Tower 2" in whats
    leaves = [row for row in rows if row[0]["what"].startswith(u"Leaves")][0]
    assert leaves[1] == report.WARN and leaves[2] == [3]
    assert report.result_rows(_Result(), labels.get, lambda i: i)[0][0]["what"] == \
        u"Nothing to do"


def test_window_xaml_has_every_named_control():
    import re
    import xml.dom.minidom
    from mepmirror import window_ui
    text = window_ui.window_xaml()
    xml.dom.minidom.parseString(text.replace(u"<!--THEME-->", u"").encode("utf-8"))
    names = set(re.findall(r'x:Name="([A-Za-z0-9_]+)"', text))
    assert set(window_ui.NAMES) <= names
    import elecui
    elecui.window_xaml(text, window_ui.ACCENTS[rules.PLUMBING])


def test_parse_mm():
    from mepmirror.window_ui import parse_mm
    assert parse_mm(u"25", 50) == 25
    assert parse_mm(u"2,5", 50) == 2.5
    assert parse_mm(u"abc", 50) == 50
    assert parse_mm(u"0", 50) == 1.0


def test_sides_without_tower2_split_by_box_only():
    from mepmirror.window_ui import sides_of

    class Model(object):
        floors = [(1, 0.0, None)]
        things = {1: _floor()}
    sides = sides_of(Model(), BOX, None, TOL)
    assert sorted(t.key for t in sides[1].tower1) == [1, 2]
    assert [t.key for t in sides[1].leaves] == [3]


def test_near_keeps_only_things_by_the_open_ends():
    things = [Thing(1, 1, (0, 0, 0), (10, 0, 0)), Thing(2, 1, (50, 50, 0)),
              Thing(3, 1, (11, 1, 0)), Thing(4, 1, (10, 0, 9))]
    assert plan.near(things, [(10.5, 0.5, 0)], 3.0) == set([1, 3])


def test_tags_row():
    from mepmirror import report
    rows = report.result_rows(_Result(tags=3), {}.get, lambda i: i)
    assert [v["what"] for v, _, _ in rows] == [u"Tags made on Tower 2's copies"]


# ---------------------------------------------------------------- firefighting

def test_fire_pipes():
    assert rules.pipe_domain(u"Fire Protection Wet", [u"FP"]) == F
    assert rules.pipe_domain(u"FireProtectWet") == F
    assert rules.pipe_domain(u"Other", [u"Sprinkler Main"]) == F
    assert rules.pipe_domain(u"Other", [u"Hose Reel"]) == F
    assert rules.pipe_domain(u"Other", [u"FHC-1"]) == F
    assert rules.pipe_domain(u"Domestic Cold Water", [u"DCW"]) == P


def test_fire_fixtures_and_pumps():
    assert rules.fixture_domain([], u"Hose Reel Cabinet : Type A") == F
    assert rules.fixture_domain([F, F], u"Cabinet") == F
    assert rules.fixture_domain([P], u"WC : Wall hung") == P
    assert rules.fixture_domain([P], u"Fire hose reel") == F      # the name wins
    assert rules.equipment_domain(0, [F, F], u"Pump") == F
    assert rules.equipment_domain(0, [], u"Fire Pump : Jockey") == F
    assert rules.equipment_domain(0, [P, F]) == P
    assert rules.equipment_domain(1, [F]) == M


def test_each_tool_has_its_categories():
    assert "OST_Sprinklers" in dict(rules.CATEGORIES[F])
    assert "OST_Sprinklers" not in dict(rules.CATEGORIES[P])
    assert rules.FIXED["OST_Sprinklers"] == F


# ---------------------------------------------------------------- electrical

def test_electrical_takes_its_own_categories():
    E = rules.ELECTRICAL
    names = dict(rules.CATEGORIES[E])
    assert "OST_ElectricalEquipment" in names and "OST_LightingFixtures" in names
    assert rules.FIXED["OST_LightingFixtures"] == E
    for other in (M, P, F):
        assert "OST_LightingFixtures" not in dict(rules.CATEGORIES[other])


def test_boards_found_by_name_are_not_mirrored_again():
    things = [Thing(1, 10, (2, 2, 9)), Thing(2, 30, (3, 3, 9)),     # light, board
              Thing(7, 31, (40, 40, 9))]                            # Tower 2's board, elsewhere
    side = plan.pair(plan.split(things, BOX, LINE, TOL), LINE, TOL)
    assert sorted(t.key for t in side.missing) == [1, 2]
    names = {2: u"CBS-B/1-F1", 7: u"CBS-B/2-F1"}
    plan.pair_by_name(side, names, (u"B1", u"B2"))
    assert side.copies == {2: 7} and side.named == set([2])
    assert [t.key for t in side.missing] == [1]
    side = plan.pair(plan.split(things, BOX, LINE, TOL), LINE, TOL)
    plan.pair_by_name(side, names, (u"", u""))
    assert len(side.missing) == 2


def test_board_and_circuit_rows():
    from copycircuits import plan as cplan
    from copycircuits.report import LevelResult, Made
    from mepmirror import report

    class Circuit(object):
        def __init__(self, label):
            self.label = label

    class Job(object):
        def __init__(self, label):
            self.circuit = Circuit(label)
            self.missing, self.already, self.elements = [], [], [1]

    c = LevelResult(u"L5", u"mirrored")
    c.made = [Made(Job(u"DB-B1/1"), 101), Made(Job(u"DB-B1/2"), 102, u"system differs")]
    c.skipped = [cplan.Skipped(Circuit(u"DB-B1/3"), cplan.ALREADY)]
    c.wires["drawn"] = 4
    c.wire_views = {u"L5 Power": 4}
    r = _Result(renamed=[(u"DB-B1", u"DB-B2")], not_renamed=[u"MCC (2)"], circuits=c)
    rows = report.result_rows(r, {}.get, lambda i: i)
    whats = dict((v["what"], (v, state, ids)) for v, state, ids in rows)
    assert whats[u"Boards named for Tower 2"][0]["item"] == u"DB-B1 -> DB-B2"
    assert whats[u"Board names to check by hand"][1] == report.WARN
    assert whats[u"Circuits made on Tower 2's boards"][2] == [101]
    assert whats[u"Circuits made but not on their board"][1] == report.WARN
    assert whats[u"Circuits already in Tower 2"][0]["count"] == u"1"
    assert whats[u"Wires"][0]["count"] == u"4"
