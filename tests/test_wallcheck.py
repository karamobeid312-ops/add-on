# -*- coding: utf-8 -*-
from wallcheck import settings
from wallcheck.check import (
    EMBEDDED, FACES_IN, FLAT, FLOATING, INSIDE, LINK_MISSING, NO_HOST, NOT_WALL, OFF_WALL, OK,
    OTHER_HOST, TILTED, UNHOSTED, UNREADABLE, Fixture, Side, check, check_all,
)
from wallcheck.report import detail, headline, notes, row, sections

WALL_200 = 0.2


def face_based(gap, on_face=True, front=0.04, back=None, square=1.0, width=WALL_200):
    """A face-based socket: its insertion point `gap` in front of the room
    face, its body from `back` (the gap by default) to gap + front."""
    back = gap if back is None else back
    room = Side(gap, on_face, gap + front, back, square)
    other = Side(-gap - width, on_face, -(back + width), -(gap + front + width), -square)
    return Fixture(1, "Socket : Double", "Electrical Fixtures", "Level 1", sides=[room, other])


def test_on_the_face():
    assert check(face_based(0.0)).status == OK
    assert check(face_based(0.008)).status == OK            # within 10 mm


def test_floating_off_the_wall():
    found = check(face_based(0.035))
    assert found.status == FLOATING
    assert abs(found.distance - 0.035) < 1e-9


def test_floating_measured_from_the_body():
    # the insertion point is on the face, but the body is modelled 50 mm off it
    found = check(face_based(0.0, front=0.09, back=0.05))
    assert found.status == FLOATING
    assert abs(found.distance - 0.05) < 1e-9


def test_back_box_reaching_the_wall_is_on_it():
    # insertion point 20 mm off, but the back box goes back to the face
    assert check(face_based(0.02, back=0.0)).status == OK


def test_embedded():
    found = check(face_based(-0.03))
    assert found.status == EMBEDDED
    assert abs(found.distance - 0.03) < 1e-9


def test_whole_fixture_inside_the_wall():
    found = check(face_based(-0.08, front=0.04))
    assert found.status == INSIDE
    assert abs(found.distance - 0.04) < 1e-9


def test_tolerance_setting():
    assert check(face_based(0.015), tolerance=0.02).status == OK
    assert check(face_based(0.015), tolerance=0.005).status == FLOATING


def test_off_the_end_of_the_wall():
    found = check(face_based(0.0, on_face=False))
    assert found.status == OFF_WALL
    assert found.distance == 0.0


def test_turned_and_facing_in():
    assert check(face_based(0.0, square=0.9)).status == TILTED
    assert abs(check(face_based(0.0, square=0.5)).distance - 60.0) < 1e-6
    assert check(face_based(0.0, square=0.9999)).status == OK
    assert check(face_based(0.0, square=-1.0)).status == FACES_IN


def test_wall_hosted_measured_by_body_only():
    # wall-hosted families: no gap, the side the body sticks out of most is theirs
    room = Side(None, True, 0.03, -0.04)                      # flush box with a back box
    other = Side(None, True, -0.16, -0.23)
    assert check(Fixture(2, sides=[other, room])).status == OK
    floating = Side(None, True, 0.08, 0.05)
    assert check(Fixture(2, sides=[floating, Side(None, True, -0.25, -0.28)])).status \
        == FLOATING
    sunk = Side(None, True, -0.02, -0.06)
    assert check(Fixture(2, sides=[sunk, Side(None, True, -0.14, -0.18)])).status == INSIDE


def test_host_kinds_and_unreadable():
    for kind in (NO_HOST, LINK_MISSING, NOT_WALL, UNHOSTED, FLAT, OTHER_HOST):
        assert check(Fixture(3, host=kind)).status == kind
    assert check(Fixture(3)).status == UNREADABLE
    assert check(Fixture(3, sides=[Side(None, True)])).status == UNREADABLE


def _result():
    fixtures = [face_based(0.0), face_based(0.035), face_based(0.05), face_based(-0.03),
                Fixture(9, "Switch : 1 Gang", "Lighting Devices", "Level 2", host=NO_HOST),
                Fixture(10, host=UNHOSTED), Fixture(11, host=FLAT), Fixture(12, host=FLAT)]
    return check_all(fixtures, 0.01)


def test_headline():
    result = _result()
    assert headline(result) == "4 of 5 wall fixtures need a look (tolerance 10 mm)."
    assert headline(check_all([face_based(0.0)])) == \
        "All 1 wall fixture on its wall, within 10 mm."
    assert headline(check_all([face_based(0.0), face_based(0.0)])) == \
        "All 2 wall fixtures on their walls, within 10 mm."
    assert headline(check_all([Fixture(1, host=FLAT)])) == "No fixtures on walls found."


def test_sections_in_order():
    found = sections(_result())
    assert [title for title, _, _ in found] == [
        "Lost their wall (1)", "Floating off the wall face (2)", "Set into the wall (1)"]
    floating = found[1][2]
    assert [round(f.distance, 3) for f in floating] == [0.05, 0.035]   # worst first


def test_details_and_rows():
    assert detail(check(face_based(0.035))) == "35 mm in front of the wall face"
    assert detail(check(face_based(-0.03))) == "insertion point 30 mm into the wall"
    assert detail(check(face_based(0.0, square=0.5))) == u"turned 60° from the wall face"
    assert row(check(face_based(0.035)), "link") == [
        "link", "Socket : Double", "Electrical Fixtures", "Level 1",
        "35 mm in front of the wall face"]


def test_notes():
    assert notes(_result()) == [
        "1 fixture not hosted (not wall-based nor face-based families): not checked.",
        "2 fixtures on ceilings, floors or roofs: not checked."]


def test_settings():
    assert settings.valid("tolerance", "5") == 5.0
    assert settings.valid("tolerance", "-1") is None
    assert settings.valid("tolerance", "abc") is None
    assert settings.coerce("tolerance", "500") == settings.DEFAULTS["tolerance"]
