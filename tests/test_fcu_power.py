# -*- coding: utf-8 -*-
import zipfile

from fcupower import match as m
from fcupower import schedule, xlsxread


def _xlsx(path, sheets):
    """A tiny .xlsx: {name: [[values]]} with shared strings and numbers."""
    strings, xml_sheets = [], []
    for rows in sheets.values():
        cells = []
        for r, row in enumerate(rows, 1):
            out = []
            for c, v in enumerate(row):
                ref = "%s%d" % (chr(65 + c), r)
                if v is None:
                    continue
                if isinstance(v, (int, float)):
                    out.append('<c r="%s"><v>%r</v></c>' % (ref, v))
                else:
                    strings.append(v)
                    out.append('<c r="%s" t="s"><v>%d</v></c>' % (ref, len(strings) - 1))
            cells.append('<row r="%d">%s</row>' % (r, "".join(out)))
        xml_sheets.append('<worksheet><sheetData>%s</sheetData></worksheet>' % "".join(cells))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook><sheets>%s</sheets></workbook>" % "".join(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (n, i, i)
            for i, n in enumerate(sheets, 1)))
        z.writestr("xl/_rels/workbook.xml.rels", "<Relationships>%s</Relationships>" % "".join(
            '<Relationship Id="rId%d" Target="worksheets/sheet%d.xml"/>' % (i, i)
            for i in range(1, len(sheets) + 1)))
        z.writestr("xl/sharedStrings.xml", "<sst>%s</sst>" % "".join(
            "<si><t>%s</t></si>" % s.replace("&", "&amp;") for s in strings))
        for i, x in enumerate(xml_sheets, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, x)


TOWER = [
    ["Fan Coil Unit Schedule"],
    ["Served Space", "Areas Served", "FCU Tag", "Qty", "Selected TCC", "Electrical Power",
     "Emergency Power", "IU Electrical Power"],
    [None, None, None, None, "kW", "kW", None, "kW"],
    ["GF-20-Corridor", "Tower-01", "T1-GF-FCU-01", 1, 5.8, 0.14, "No", "-"],
    ["GF-87-Corridor", "Tower-01", "T1-GF-FCU-06", 2, 9.08, 0.24, "No", "-"],
    ["Future Expansion", "Tower-01", "T1-L1-FCU", "-", "-", "-", "No", "-"],
    ["L2-26-Lift Lobby", "Tower-01", "T1-L2-FCU-01", 1, 2.58, 0.046, "No", "-"],
    ["Notes: all units R&D"],
]
TOWER2 = [
    ["Fan Coil Unit Schedule"],
    ["Served Space", "Areas Served", "FCU Tag", "Qty", "Selected TCC", "Electrical Power"],
    [None, None, None, None, "kW", "kW"],
    ["L2-26-Lift Lobby", "Tower-02", "T1-L2-FCU-01", 1, 2.58, 0.06],
]


def _sheets(tmp_path):
    path = str(tmp_path / "s.xlsx")
    _xlsx(path, {"Tower-01": TOWER, "Tower-02": TOWER2})
    return schedule.sheets(xlsxread.read(path))


def test_reader_and_columns(tmp_path):
    t1, t2 = _sheets(tmp_path)
    assert t1.name == "Tower-01" and t1.rows[3][2] == "T1-GF-FCU-01"
    assert t1.tag.label == "FCU Tag" and t1.room.label == "Served Space"
    assert t1.power.label == "Electrical Power (kW)" and t1.unit == "kW"
    assert t1.qty.label == "Qty"
    rows = t1.fcu_rows()
    assert [r.tag for r in rows] == ["T1-GF-FCU-01", "T1-GF-FCU-06", "T1-L1-FCU", "T1-L2-FCU-01"]
    assert rows[0].watts == 140 and rows[3].watts == 46 and rows[2].watts is None
    assert rows[0].number == 4
    assert [r.watts for r in t1.fcu_rows(unit="W")][:2] == [0.14, 0.24]


def test_units():
    assert schedule.unit_of("Electrical Power (kW)") == "kW"
    assert schedule.unit_of("Power [W]") == "W"
    assert schedule.unit_of("POWER (V/Ph/Hz)") == "V/Ph/Hz"
    assert schedule.number("1,250") == 1250 and schedule.number("-") is None


def test_tags_and_rooms():
    assert m.tag_key("T1-GF-FCU-01") == m.tag_key("t1 gf fcu 1")
    assert m.tag_key("FCU-10") != m.tag_key("FCU-1")
    assert m.room_match("GF-20-Corridor", "GF-20", "CORRIDOR") == m.FULL
    assert m.room_match("GF-20-Corridor", "20", "Corridor") == m.FULL
    assert m.room_match("GF-20-Corridor", "21", "Corridor") == m.PARTIAL
    assert m.room_match("GF-20-Corridor", "05", "Lobby") == m.NONE
    assert m.room_match("GF-20-Corridor", "", "") == m.UNKNOWN


def test_match(tmp_path):
    t1, t2 = _sheets(tmp_path)
    rows = t1.fcu_rows() + t2.fcu_rows()
    fcus = [
        m.Fcu(1, "T1-GF-FCU-01", "GF-20", "Corridor"),
        m.Fcu(2, "T1-GF-FCU-06", "GF-87", "Corridor", current=240),
        m.Fcu(3, "T1-GF-FCU-06", "GF-87", "Corridor"),
        m.Fcu(4, "T1-GF-FCU-06", "GF-87", "Corridor"),
        m.Fcu(5, "T1-L2-FCU-01", "L2-26", "Lift Lobby"),
        m.Fcu(6, ""),
        m.Fcu(7, "T9-FCU-01", "1", "X"),
        m.Fcu(9, "T1-L1-FCU", "L1-1", "Future"),
    ]
    unused = m.match(fcus, rows)
    f = dict((x.key, x) for x in fcus)
    assert f[1].write and f[1].watts == 140 and f[1].state == m.OK
    assert not f[2].write and f[2].status.startswith("Already set")
    assert f[3].write and f[3].state == m.WARN and "Qty 2" in f[3].status   # 3 in model
    assert f[5].state == m.BAD and "differ" in f[5].status and not f[5].write
    assert f[6].state == m.BAD and f[6].status == "No tag in Comments"
    assert f[7].state == m.BAD and f[7].status == "Tag not in the schedule"
    assert f[9].state == m.BAD and "No power" in f[9].status
    assert unused == []
    s = m.summary(fcus, unused)
    assert s["write"] == 3 and s["bad"] == 4 and s["same"] == 1
    other = m.Fcu(8, "T1-GF-FCU-01", "GF-05", "Lobby")
    m.match([other], rows)
    assert other.state == m.WARN and other.write and "Room differs" in other.status
    missing = m.Fcu(10, "t1 gf fcu 1", "GF-20", "Corridor", has_param=False)
    m.match([missing], rows)
    assert missing.state == m.BAD and not missing.write


def test_unused_rows(tmp_path):
    t1, _ = _sheets(tmp_path)
    unused = m.match([m.Fcu(1, "T1-GF-FCU-01", "GF-20", "Corridor")], t1.fcu_rows())
    assert [r.tag for r in unused] == ["T1-GF-FCU-06", "T1-L1-FCU", "T1-L2-FCU-01"]
