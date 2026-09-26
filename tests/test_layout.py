from sld.layout import BOTTOM, CENTER, DOWN, UP, LayoutOptions, layout_diagram
from sld.model import CircuitInfo, EquipmentInfo, build_diagram


def sample(include_branch=False):
    equipment = [EquipmentInfo(i, i) for i in ["MSB", "DP-1", "DP-2", "LP-1", "LP-2", "LP-3"]]
    circuits = [
        CircuitInfo("f1", "MSB", "1", fed_equipment_ids=["DP-1"]),
        CircuitInfo("f2", "MSB", "2", fed_equipment_ids=["DP-2"]),
        CircuitInfo("f3", "DP-1", "1", fed_equipment_ids=["LP-1"]),
        CircuitInfo("f4", "DP-1", "2", fed_equipment_ids=["LP-2"]),
        CircuitInfo("f5", "DP-2", "1", fed_equipment_ids=["LP-3"]),
        CircuitInfo("b1", "LP-1", "1", load_name="Lights", branch_load_count=3),
        CircuitInfo("b2", "LP-1", "2", load_name="Recs", branch_load_count=3),
    ]
    return build_diagram(equipment, circuits, include_branch)


def overlaps(a, b):
    return a.left < b.right - 1e-9 and b.left < a.right - 1e-9 and a.top_y == b.top_y


def test_no_boxes_overlap_on_same_row():
    for direction in (UP, DOWN):
        for include in (False, True):
            opts = LayoutOptions(direction=direction)
            placements = list(layout_diagram(sample(include), options=opts).placements.values())
            for i, a in enumerate(placements):
                for b in placements[i + 1:]:
                    assert not overlaps(a, b), (a.node.title, b.node.title)


def test_default_grows_bottom_to_top():
    opts = LayoutOptions()
    assert opts.direction == UP
    p = layout_diagram(sample(), options=opts).placements
    assert abs(p["MSB"].center_x - (p["DP-1"].center_x + p["DP-2"].center_x) / 2) < 1e-9
    # source on the bottom row, each level one row higher
    assert p["MSB"].bottom == 0
    assert p["DP-1"].bottom == opts.row_pitch
    assert p["LP-1"].bottom == 2 * opts.row_pitch
    assert p["MSB"].top_y < p["DP-1"].bottom


def test_down_direction_grows_top_to_bottom():
    opts = LayoutOptions(direction=DOWN)
    p = layout_diagram(sample(), options=opts).placements
    assert p["MSB"].top_y == 0
    assert p["DP-1"].top_y == -opts.row_pitch
    assert p["LP-1"].top_y == -2 * opts.row_pitch


def test_every_child_has_a_feeder_reaching_its_near_edge():
    for direction in (UP, DOWN):
        d = sample(True)
        drawing = layout_diagram(d, options=LayoutOptions(direction=direction))
        for node in d.iter_nodes():
            if node.feeder is None:
                continue
            k = drawing.placements[node.id]
            assert any(abs(l.x1 - k.center_x) < 1e-9 and abs(l.x2 - k.center_x) < 1e-9
                       and abs(l.y2 - k.near_y) < 1e-9 for l in drawing.lines), node.title


def test_up_feeders_leave_from_top_of_parent():
    drawing = layout_diagram(sample())
    msb = drawing.placements["MSB"]
    assert any(abs(l.x1 - msb.center_x) < 1e-9 and abs(l.y1 - msb.top_y) < 1e-9
               and l.y2 > l.y1 for l in drawing.lines)
    # nothing is drawn below the source except the title
    assert min(min(l.y1, l.y2) for l in drawing.lines) == msb.bottom


def test_title_and_node_text():
    drawing = layout_diagram(sample(), title="SLD", subtitle="today")
    titles = [t for t in drawing.texts if t.text == "SLD\ntoday"]
    assert len(titles) == 1 and titles[0].y < 0  # under the sources
    assert any(t.text.startswith("MSB") and t.align == CENTER for t in drawing.texts)
    labels = [t for t in drawing.texts if t.text.startswith("CKT 1")]
    assert labels and all(t.valign == BOTTOM for t in labels)


def test_unknown_option_rejected():
    for kwargs in ({"nope": 1}, {"direction": "sideways"}):
        try:
            LayoutOptions(**kwargs)
        except (TypeError, ValueError):
            continue
        assert False, kwargs
