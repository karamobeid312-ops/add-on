from sld.layout import CENTER, LayoutOptions, layout_diagram
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
    for include in (False, True):
        placements = list(layout_diagram(sample(include)).placements.values())
        for i, a in enumerate(placements):
            for b in placements[i + 1:]:
                assert not overlaps(a, b), (a.node.title, b.node.title)


def test_parent_centered_over_children_and_rows_descend():
    opts = LayoutOptions()
    d = sample()
    p = layout_diagram(d, options=opts).placements
    assert abs(p["MSB"].center_x - (p["DP-1"].center_x + p["DP-2"].center_x) / 2) < 1e-9
    assert p["MSB"].top_y == 0
    assert p["DP-1"].top_y == -opts.row_pitch
    assert p["LP-1"].top_y == -2 * opts.row_pitch


def test_every_child_has_a_drop_reaching_its_top():
    d = sample(True)
    drawing = layout_diagram(d)
    for node in d.iter_nodes():
        if node.feeder is None:
            continue
        k = drawing.placements[node.id]
        assert any(abs(l.x1 - k.center_x) < 1e-9 and abs(l.x2 - k.center_x) < 1e-9
                   and abs(l.y2 - k.top_y) < 1e-9 for l in drawing.lines), node.title


def test_title_and_node_text():
    drawing = layout_diagram(sample(), title="SLD", subtitle="today")
    texts = [t.text for t in drawing.texts]
    assert "SLD\ntoday" in texts
    assert any(t.startswith("MSB") and t_.align == CENTER for t, t_ in zip(texts, drawing.texts))
    assert any(t.startswith("CKT 1") for t in texts)


def test_unknown_option_rejected():
    try:
        LayoutOptions(nope=1)
    except TypeError:
        return
    assert False
