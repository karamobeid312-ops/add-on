from sld.model import (BRANCH_CIRCUIT, EQUIPMENT, CircuitInfo, EquipmentInfo,
                       build_diagram, natural_key)


def eq(i):
    return EquipmentInfo(i, i)


def names(nodes):
    return [n.title for n in nodes]


def test_builds_hierarchy_from_feeders():
    equipment = [eq("MSB"), eq("LP-1"), eq("LP-2"), eq("DP-1")]
    circuits = [
        CircuitInfo("c1", "MSB", "1,3,5", fed_equipment_ids=["DP-1"]),
        CircuitInfo("c2", "DP-1", "2,4,6", fed_equipment_ids=["LP-2"]),
        CircuitInfo("c3", "DP-1", "1,3,5", fed_equipment_ids=["LP-1"]),
    ]
    d = build_diagram(equipment, circuits)
    assert names(d.roots) == ["MSB"]
    dp = d.roots[0].children[0]
    assert dp.title == "DP-1" and dp.feeder.id == "c1"
    # children ordered by circuit number
    assert names(dp.children) == ["LP-1", "LP-2"]
    assert d.warnings == []


def test_unfed_equipment_become_separate_roots():
    d = build_diagram([eq("B"), eq("A")], [])
    assert names(d.roots) == ["A", "B"]


def test_branch_circuits_only_when_requested():
    equipment = [eq("LP-1")]
    circuits = [
        CircuitInfo("c1", "LP-1", "3", load_name="Lighting", rating="20 A", poles="1",
                    branch_load_count=4),
        CircuitInfo("c2", "LP-1", "1", load_name="Receptacles", branch_load_count=2),
        CircuitInfo("c3", "LP-1", "5", load_name="Spare", branch_load_count=0),
    ]
    assert build_diagram(equipment, circuits).roots[0].children == []

    kids = build_diagram(equipment, circuits, include_branch_circuits=True).roots[0].children
    assert names(kids) == ["Receptacles", "Lighting"]
    assert all(k.kind == BRANCH_CIRCUIT for k in kids)
    assert kids[1].details[0] == "CKT 3, 20 A / 1P"


def test_feed_loop_is_broken_with_warning():
    circuits = [
        CircuitInfo("c1", "A", "1", fed_equipment_ids=["B"]),
        CircuitInfo("c2", "B", "1", fed_equipment_ids=["A"]),
    ]
    d = build_diagram([eq("A"), eq("B")], circuits)
    all_ids = [n.id for n in d.iter_nodes()]
    assert sorted(all_ids) == ["A", "B"]
    assert len(d.warnings) == 1 and "loop" in d.warnings[0]


def test_double_fed_equipment_warns_and_appears_once():
    circuits = [
        CircuitInfo("c1", "A", "1", fed_equipment_ids=["C"]),
        CircuitInfo("c2", "B", "2", fed_equipment_ids=["C"]),
    ]
    d = build_diagram([eq("A"), eq("B"), eq("C")], circuits)
    assert [n.id for n in d.iter_nodes()].count("C") == 1
    assert any("more than one circuit" in w for w in d.warnings)


def test_ignores_circuits_from_unknown_sources_and_self_feeds():
    circuits = [
        CircuitInfo("c1", "ghost", "1", fed_equipment_ids=["A"]),
        CircuitInfo("c2", "A", "1", fed_equipment_ids=["A"]),
    ]
    d = build_diagram([eq("A")], circuits)
    assert names(d.roots) == ["A"] and d.roots[0].children == []
    assert d.roots[0].kind == EQUIPMENT


def test_natural_key():
    assert sorted(["10", "2", "1,3,5", "B", "a"], key=natural_key) == ["1,3,5", "2", "10", "a", "B"]


def test_feeder_label():
    c = CircuitInfo("c", "s", "1,3,5", rating="100 A", poles="3", wire_size="4#1, 1#6G")
    assert c.feeder_label_lines() == ["CKT 1,3,5", "100 A / 3P", "4#1, 1#6G"]
