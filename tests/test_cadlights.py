import math

from cadlights.match import (Block, Result, clean_name, group, normal_angle, split_spots,
                             summarize)


def test_clean_name_drops_dwg_prefix():
    assert clean_name("Plan-L1.dwg.LT-600") == "LT-600"
    assert clean_name("PLAN.DWG.Down Light") == "Down Light"
    assert clean_name("LT-600") == "LT-600"
    assert clean_name("") == "(unnamed block)"


def test_clean_name_drops_dynamic_block_variant():
    assert clean_name("SEC-Lighting Fixture-600x600mm - 600x600mm-V457-L2") == \
        "SEC-Lighting Fixture-600x600mm - 600x600mm"
    assert clean_name("SEC-Lighting Fixture-Linear - LED 75w x82d Functional-V108-GROUND") == \
        "SEC-Lighting Fixture-Linear - LED 75w x82d Functional"
    assert clean_name("SEC-Lighting Fixture-Linear - LED 75w x82d Functional-V52-L2") == \
        "SEC-Lighting Fixture-Linear - LED 75w x82d Functional"
    assert clean_name("LT-V2") == "LT"
    assert clean_name("DOWNLIGHT-VERTICAL") == "DOWNLIGHT-VERTICAL"


def test_normal_angle():
    assert normal_angle(-math.pi / 2) == math.pi * 1.5
    assert normal_angle(2 * math.pi) == 0.0


def test_group_most_first_with_layers():
    blocks = [Block("A", 0, 0, layer="E-LT"), Block("B", 1, 1), Block("B", 2, 2, layer="L2"),
              Block("B", 3, 3, layer="L1")]
    rows = group(blocks)
    assert [(n, len(b), l) for n, b, l in rows] == [("B", 3, ["L1", "L2"]), ("A", 1, ["E-LT"])]


def test_split_spots_existing_and_duplicates():
    tol = 50 / 304.8
    blocks = [Block("A", 10, 10), Block("A", 10.1, 10), Block("A", 20, 20),
              Block("A", 20 + tol * 0.5, 20)]
    new, already = split_spots(blocks, [(10.0, 10.0 + tol * 0.9)], tol)
    # 10,10 is near the existing light; 10.1,10 is 54 mm from it -> new;
    # the last block sits on the 20,20 one -> already
    assert [(b.x, b.y) for b in new] == [(10.1, 10), (20, 20)]
    assert len(already) == 2


def test_split_spots_far_apart_all_new():
    blocks = [Block("A", i * 2.0, 0) for i in range(5)]
    new, already = split_spots(blocks, [], 50 / 304.8)
    assert len(new) == 5 and not already


def test_summary():
    r = Result("LT-600", "Panel : 600x600")
    r.placed, r.already, r.on_slab = 10, 2, 1
    r.fail("no ceiling above to host it")
    head, details = summarize([r], ["NOTE"])
    assert head == "Placed 10 lights. 2 spots already had a light, 1 could not be placed."
    assert "LT-600 -> Panel : 600x600: 10 placed (1 under the slab, no ceiling), 2 already there" \
        in details
    assert "1 not placed: no ceiling above to host it" in details
    assert "Skipped blocks: NOTE" in details


def test_summary_timings():
    _, details = summarize([], [], [("read CAD", 0.25), ("place", 12.0)])
    assert details.endswith("Time: read CAD 0.2 s, place 12.0 s") or \
        details.endswith("Time: read CAD 0.3 s, place 12.0 s")


def test_summary_level_based_note():
    r = Result("LT", "Light : A")
    r.kind = "level-based"
    _, details = summarize([r], [])
    assert "level-based, so Revit cannot host it" in details
