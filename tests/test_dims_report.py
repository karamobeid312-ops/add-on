# -*- coding: utf-8 -*-
from dims import settings
from dims.report import Run, summarize


def test_all_well():
    run = Run("Level 1 - RCP", 24)
    run.made = list(range(7))
    headline, details = summarize(run)
    assert headline == "7 dimension strings added in 'Level 1 - RCP' for 24 devices."
    assert details == ""


def test_one_of_each():
    run = Run("L1", 1)
    run.made = [1]
    run.replaced = 1
    headline, _ = summarize(run)
    assert headline == "1 dimension string added in 'L1' for 1 device. 1 old dimension replaced."


def test_notes():
    run = Run("L1", 10)
    run.made = [1, 2]
    run.notes = {("Detector : Smoke", "no Center (Front/Back) reference plane in the family, "
                                      "dimensioned one way only"): 3}
    run.hidden, run.alone, run.no_wall, run.skew, run.no_walls = 2, 1, 4, 2, 1
    run.failed = ["Invalid number of references.", "Invalid number of references."]
    run.type_missing = "Linear - 2.5mm Arial"
    run.dims_hidden = True
    headline, details = summarize(run)
    assert headline.endswith("See the notes.")
    lines = details.split("\n")
    assert lines[0] == ("Detector : Smoke (3): no Center (Front/Back) reference plane in the "
                        "family, dimensioned one way only.")
    assert lines[1].startswith("2 devices selected but not shown in this view")
    assert lines[2].startswith("1 device not dimensioned along one direction")
    assert lines[3].startswith("4 string ends with no wall found")
    assert lines[4].startswith("2 string ends at a wall that is not square")
    assert lines[5].startswith("1 string made without some of their walls")
    assert lines[6] == "2 strings not made: Invalid number of references."
    assert "'Linear - 2.5mm Arial' is not in this model" in lines[7]
    assert lines[8].startswith("Dimensions are hidden in this view")


def test_nothing_made():
    run = Run("L1", 3)
    run.failed = ["boom"]
    headline, details = summarize(run)
    assert headline == "No dimension strings added in 'L1'. See the notes."
    assert details == "1 string not made: boom"


def test_settings_values():
    assert settings.valid("offset", "7.5") == 7.5
    assert settings.valid("offset", "0") == 0.0
    assert settings.valid("offset", "-1") is None
    assert settings.valid("offset", "51") is None
    assert settings.valid("offset", "abc") is None
    assert settings.valid("strings", "needed") == "needed"
    assert settings.valid("strings", "some") is None
    assert settings.valid("ends", "none") == "none"
    assert settings.valid("ends", "walls") is None
    assert settings.DEFAULTS["ends"] == "nearest"
    assert settings.valid("dim_type", "Linear - 2.5mm Arial") == "Linear - 2.5mm Arial"
    assert settings.coerce("offset", "x") == settings.DEFAULTS["offset"]
    assert settings.coerce("ends", None) == "nearest"
