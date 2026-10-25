# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons of the LOD panel."""
import os

from pyrevit import forms, revit, script

from lod import excel, export, keyplan, revit_lod, settings
from lod.compare import Change, compare
from lod.table import NoTable, pick_sheet, sheet_name

TITLE = "LOD"


# ------------------------------------------------------------ common

def _doc():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to use the LOD tools.", title=TITLE)
        return None
    return doc


def _pick_lod(values, ask=True):
    """Path of the LOD workbook: the last one, or picked."""
    last = values.get("lod_path") or ""
    if last and os.path.exists(last):
        if not ask:
            return last
        choice = forms.CommandSwitchWindow.show(
            [u"Use %s" % os.path.basename(last), u"Pick another LOD file"],
            message=u"Which List of Deliverables?")
        if not choice:
            return None
        if choice.startswith(u"Use "):
            return last
    path = forms.pick_file(files_filter="Excel workbooks (*.xlsx;*.xlsm;*.xls)|*.xlsx;*.xlsm;*.xls",
                           init_dir=os.path.dirname(last) if last else "",
                           title="Pick the List of Deliverables")
    if path:
        values["lod_path"] = path
        settings.save(values)
    return path


def _read_lod(path):
    try:
        with forms.ProgressBar(title="Reading %s..." % os.path.basename(path), indeterminate=True):
            sheets = excel.read_sheets(path)
    except excel.ExcelMissing as error:
        forms.alert(u"%s. The LOD is read with Excel." % error, title=TITLE)
        return None
    except Exception as error:
        forms.alert(u"Could not read %s:\n%s" % (os.path.basename(path), error), title=TITLE)
        return None
    try:
        return pick_sheet(sheets)
    except NoTable as error:
        forms.alert(u"%s" % error, title=TITLE)
        return None


def _load_lod(values, ask=True):
    path = _pick_lod(values, ask)
    return _read_lod(path) if path else None


def _rules(values):
    try:
        return keyplan.parse_rules(values.get("keyplan_rules"))
    except keyplan.RuleError as error:
        forms.alert(u"%s\n\nFix them in LOD Settings > Key plan rules." % error, title=TITLE)
        return None


def _keyplan_fn(rules):
    return lambda name: keyplan.values(name, rules)


def _sheets(doc, values):
    return revit_lod.sheets(doc, values["rev_param"], values["area_param"])


def _out(title):
    output = script.get_output()
    output.set_title(title)
    return output


def _duplicates_note(output, table):
    dups = table.duplicates()
    if dups:
        output.print_md("## Repeated numbers in the LOD")
        output.print_md("*A Revit sheet number must be unique, so only the first drawing "
                        "with each of these numbers is used.*")
        output.print_table(
            table_data=[[n, len(ds), u"<br>".join(d.title for d in ds)]
                        for n, ds in sorted(dups.items())],
            columns=["Number", "Times", "Titles"])


def _choose_title_block(doc, values):
    blocks = revit_lod.title_blocks(doc)
    if not blocks:
        forms.alert("Load a title block family first.", title=TITLE)
        return None
    name = values.get("title_block")
    if name in blocks:
        return blocks[name]
    name = forms.SelectFromList.show(sorted(blocks), title="Title block for the new sheets",
                                     button_name="Use this title block")
    if not name:
        return None
    values["title_block"] = name
    settings.save(values)
    return blocks[name]


# ------------------------------------------------------------ Create Sheets

def create_sheets():
    """Create a Revit sheet for every LOD drawing the model does not have yet."""
    doc = _doc()
    if doc is None:
        return
    values = settings.load()
    table = _load_lod(values)
    if table is None:
        return
    existing = set(s.number for s in _sheets(doc, values))
    todo, seen = [], set()
    for d in table.drawings:
        if d.number in existing or d.number in seen:
            continue
        seen.add(d.number)
        todo.append(d)
    if not todo:
        forms.alert(u"Every drawing of the LOD (%d) already has a sheet in this model."
                    % len(table.by_number()), title=TITLE)
        return
    prefix = values["title_prefix"]
    labels = [u"%s   %s" % (d.number, sheet_name(d.title, prefix)) for d in todo]
    picked = forms.SelectFromList.show(
        [forms.TemplateListItem(label, checked=True) for label in labels],
        title=u"Create %d sheets (untick the ones to skip)" % len(todo),
        multiselect=True, button_name="Create sheets")
    if not picked:
        return
    picked = set(picked)
    todo = [d for d, label in zip(todo, labels) if label in picked]
    title_block = _choose_title_block(doc, values)
    if title_block is None:
        return
    rules = None
    if forms.alert("Set the key plan of the new sheets from their names too?",
                   title=TITLE, yes=True, no=True):
        rules = _rules(values)
        if rules is None:
            return
    items = [(d.number, sheet_name(d.title, prefix), d.rev, d.area) for d in todo]
    made, failed, notes = revit_lod.create_sheets(
        doc, items, title_block, values["rev_param"], values["area_param"],
        _keyplan_fn(rules) if rules else None)

    output = _out("Create Sheets")
    output.print_md("# Sheets created from the LOD")
    output.print_md(u"**%d** sheet%s created from *%s*." % (
        len(made), "" if len(made) == 1 else "s", os.path.basename(values["lod_path"])))
    if made:
        output.print_table(table_data=[[n, output.linkify(i)] for n, i in made],
                           columns=["Number", "Sheet"])
    if failed:
        output.print_md("## Not created")
        output.print_table(table_data=[list(f) for f in failed], columns=["Number", "Why"])
    _print_param_notes(output, notes)
    _duplicates_note(output, table)


def _print_param_notes(output, notes):
    if not notes:
        return
    grouped = {}
    for number, param, why in notes:
        grouped.setdefault((param, why), []).append(number)
    output.print_md("## Parameters not set")
    output.print_md("*Add the missing parameters to the sheets / title block, or change the "
                    "names in LOD Settings.*")
    output.print_table(
        table_data=[[p, w, len(ns), u", ".join(ns[:5]) + (u"..." if len(ns) > 5 else u"")]
                    for (p, w), ns in sorted(grouped.items())],
        columns=["Parameter", "Why", "Sheets", "First sheets"])


# ------------------------------------------------------------ Compare / Sync

def _report(output, result, table, values):
    output.print_md(u"LOD *%s*, sheet *%s*: **%d** drawings; model: **%d** matching sheets."
                    % (os.path.basename(values["lod_path"]), table.sheet_name,
                       len(table.by_number()), len(result.matched)))
    if result.in_step():
        output.print_md("**The sheets match the LOD.**")
    if result.missing:
        output.print_md("## In the LOD, not in Revit (%d)" % len(result.missing))
        output.print_table(table_data=[[d.number, d.rev, d.title] for d in result.missing],
                           columns=["Number", "Rev.", "LOD title"])
    if result.extra:
        output.print_md("## In Revit, not in the LOD (%d)" % len(result.extra))
        output.print_table(
            table_data=[[s.number, s.name, output.linkify(s.key)] for s in result.extra],
            columns=["Number", "Sheet name", "Sheet"])
    for field, heading in ((Change.NAME, "Different name"), (Change.REV, "Different revision"),
                           (Change.AREA, "Different area")):
        changes = result.by_field(field)
        if changes:
            output.print_md("## %s (%d)" % (heading, len(changes)))
            output.print_table(
                table_data=[[c.sheet.number, c.old, c.new, output.linkify(c.sheet.key)]
                            for c in changes],
                columns=["Number", "In Revit", "In the LOD", "Sheet"])
    if result.no_rev_param:
        output.print_md(u"*%d sheet%s have no '%s' parameter: add it to the Sheets category "
                        u"(Text) to keep the LOD revision on the sheets.*"
                        % (len(result.no_rev_param), "" if len(result.no_rev_param) == 1 else "s",
                           values["rev_param"]))
    _duplicates_note(output, table)


def _compare(doc, values, table):
    return compare(table, _sheets(doc, values), values["title_prefix"],
                   use_rev=bool(values["rev_param"]), use_area=bool(values["area_param"]))


def compare_lod():
    """Report the differences between the LOD and the sheets."""
    doc = _doc()
    if doc is None:
        return
    values = settings.load()
    table = _load_lod(values)
    if table is None:
        return
    result = _compare(doc, values, table)
    output = _out("Compare LOD")
    output.print_md("# LOD against the Revit sheets")
    _report(output, result, table, values)


def sync_lod():
    """Bring the sheet names, revisions (and areas) in line with the LOD."""
    doc = _doc()
    if doc is None:
        return
    values = settings.load()
    table = _load_lod(values)
    if table is None:
        return
    result = _compare(doc, values, table)
    if not result.changes:
        msg = u"The names and revisions of the %d matching sheets already follow the LOD." \
              % len(result.matched)
        if result.missing:
            msg += u"\n\n%d LOD drawings have no sheet yet: use Create Sheets." % len(result.missing)
        forms.alert(msg, title=TITLE)
        return
    labels = [c.label() for c in result.changes]
    picked = forms.SelectFromList.show(
        [forms.TemplateListItem(label, checked=True) for label in labels],
        title=u"%d changes from the LOD (untick the ones to skip)" % len(labels),
        multiselect=True, button_name="Apply to the sheets")
    if not picked:
        return
    picked = set(picked)
    changes = [c for c, label in zip(result.changes, labels) if label in picked]
    failed = revit_lod.apply_changes(doc, changes, values["rev_param"], values["area_param"])
    output = _out("Sync LOD")
    output.print_md("# Sheets updated from the LOD")
    output.print_md(u"**%d** change%s applied." % (len(changes) - len(failed),
                                                    "" if len(changes) - len(failed) == 1 else "s"))
    done = [c for c in changes if c not in set(f[0] for f in failed)]
    if done:
        output.print_table(
            table_data=[[c.sheet.number, c.field, c.old, c.new, output.linkify(c.sheet.key)]
                        for c in done],
            columns=["Number", "What", "Was", "Now", "Sheet"])
    if failed:
        output.print_md("## Not changed")
        output.print_table(table_data=[[c.sheet.number, c.field, c.new, why] for c, why in failed],
                           columns=["Number", "What", "LOD value", "Why"])
    if result.missing:
        output.print_md(u"*%d LOD drawings have no sheet yet: use Create Sheets.*"
                        % len(result.missing))


# ------------------------------------------------------------ Export

FROM_LOD = "Update the LOD from Revit (keep its order and stages)"
FROM_MODEL = "New LOD from the Revit sheets only"


def export_lod():
    """Write the LOD from the Revit sheets as a new .xlsx."""
    doc = _doc()
    if doc is None:
        return
    values = settings.load()
    choice = forms.CommandSwitchWindow.show([FROM_LOD, FROM_MODEL], message="Export the LOD:")
    if not choice:
        return
    table = None
    if choice == FROM_LOD:
        table = _load_lod(values)
        if table is None:
            return
    sheets = _sheets(doc, values)
    if not [s for s in sheets if not s.placeholder]:
        forms.alert("This model has no sheets.", title=TITLE)
        return
    project = u""
    try:
        project = doc.ProjectInformation.Name or u""
    except Exception:
        pass
    default = u"%s Electrical LOD.xlsx" % project if project else u"Electrical LOD.xlsx"
    path = forms.save_file(file_ext="xlsx", default_name=default)
    if not path:
        return
    if values["lod_path"] and os.path.normcase(path) == os.path.normcase(values["lod_path"]):
        forms.alert("Save the export as a new file, not over the LOD it was made from.",
                    title=TITLE)
        return
    book = export.workbook(sheets, table, values["title_prefix"], project)
    try:
        book.save(path)
    except Exception as error:
        forms.alert(u"Could not save %s:\n%s\n\nIs it open in Excel?" % (path, error), title=TITLE)
        return
    counts = export.summary(sheets, table, values["title_prefix"])
    output = _out("Export LOD")
    output.print_md("# LOD exported")
    output.print_md(u"Saved **%s**." % path)
    output.print_table(
        table_data=[[status or u"Unchanged", n] for status, n in sorted(counts.items())],
        columns=["Status", "Drawings"])
    if forms.alert("LOD saved. Open it now?", title=TITLE, yes=True, no=True):
        os.startfile(path)


# ------------------------------------------------------------ Key plans

ALL = "All sheets"
SELECTED = "Sheets selected in the Project Browser"
ACTIVE = "This sheet"


def keyplans():
    """Switch the key plan of the sheets from their names."""
    doc, uidoc = _doc(), revit.uidoc
    if doc is None:
        return
    values = settings.load()
    rules = _rules(values)
    if rules is None:
        return
    options = [ALL]
    if revit_lod.selected_sheets(doc, uidoc):
        options.insert(0, SELECTED)
    from Autodesk.Revit.DB import ViewSheet
    if isinstance(doc.ActiveView, ViewSheet):
        options.insert(0, ACTIVE)
    choice = forms.CommandSwitchWindow.show(options, message="Set the key plan of:")
    if not choice:
        return
    if choice == ACTIVE:
        targets = [doc.ActiveView]
    elif choice == SELECTED:
        targets = revit_lod.selected_sheets(doc, uidoc)
    else:
        targets = revit_lod.all_sheets(doc)
    done, problems = revit_lod.switch_keyplans(doc, targets, _keyplan_fn(rules))
    output = _out("Key Plans")
    output.print_md("# Key plans set from the sheet names")
    output.print_md(u"**%d** sheet%s done." % (done, "" if done == 1 else "s"))
    if len(targets) <= 40:
        rows = []
        for s in targets:
            on = [p for p, v in keyplan.values(s.Name, rules) if v is True]
            text = [u"%s = %s" % (p, v) for p, v in keyplan.values(s.Name, rules)
                    if not isinstance(v, bool)]
            rows.append([s.SheetNumber, s.Name, u", ".join(on) or u"-", u", ".join(text)])
        output.print_table(table_data=rows, columns=["Number", "Name", "On", "Text"])
    if problems:
        grouped = {}
        for sheet, param, why in problems:
            grouped.setdefault((param, why), []).append(sheet)
        output.print_md("## Not set")
        output.print_md("*Use LOD Settings > Show the parameters of this sheet to see the "
                        "parameter names of your title block / key plan, then edit the key plan "
                        "rules to match them.*")
        output.print_table(
            table_data=[[p, w, len(ss), output.linkify([s.Id for s in ss[:50]],
                                                       u"Select %d" % min(len(ss), 50))]
                        for (p, w), ss in sorted(grouped.items(), key=lambda i: i[0])],
            columns=["Parameter", "Why", "Sheets", ""])


# ------------------------------------------------------------ Settings

# ------------------------------------------------------------ Place Views

class _PairItem(forms.TemplateListItem):
    @property
    def name(self):
        sheet, view = self.item
        return u"%s  %s   <-   %s" % (sheet.SheetNumber, sheet.Name, view.Name)


def place_views():
    """Put on each sheet the view named after its LOD title."""
    from lod import placeviews
    doc, uidoc = _doc(), revit.uidoc
    if doc is None:
        return
    values = settings.load()
    options = [ALL]
    if revit_lod.selected_sheets(doc, uidoc):
        options.insert(0, SELECTED)
    from Autodesk.Revit.DB import ViewSheet
    if isinstance(doc.ActiveView, ViewSheet):
        options.insert(0, ACTIVE)
    choice = forms.CommandSwitchWindow.show(options, message="Place the views on:")
    if not choice:
        return
    if choice == ACTIVE:
        targets = [doc.ActiveView]
    elif choice == SELECTED:
        targets = revit_lod.selected_sheets(doc, uidoc)
    else:
        targets = revit_lod.all_sheets(doc)

    views = revit_lod.view_list(doc)
    view_by_id = revit_lod.views_by_id(doc)
    on_sheets = dict((i, on) for i, _, on in views)
    sheet_by_id = dict((revit_lod.id_int(s.Id), s) for s in revit_lod.all_sheets(doc))
    found = placeviews.match([(revit_lod.id_int(s.Id), s.Name) for s in targets],
                             views, values.get("title_prefix", u""))

    todo, already, elsewhere, missing = [], [], [], []
    for s in targets:
        sid = revit_lod.id_int(s.Id)
        ids = found.get(sid)
        if not ids:
            missing.append(s)
            continue
        best = view_by_id[ids[0]]
        on = on_sheets.get(ids[0]) or set()
        if sid in on:
            already.append((s, best))
        elif on and u"%s" % best.ViewType != u"Legend":
            others = [sheet_by_id[o] for o in on if o in sheet_by_id]
            elsewhere.append((s, best, u", ".join(o.SheetNumber for o in others)))
        else:
            todo.append((s, best))

    placed, failed = [], []
    if todo:
        picked = forms.SelectFromList.show(
            [_PairItem(p, checked=True) for p in todo], multiselect=True,
            title="Place these views on their sheets", button_name="Place views",
            width=900, height=600)
        if not picked:
            return
        placed, failed = revit_lod.place_views(doc, picked)

    output = _out("Place Views")
    output.print_md("# Views placed on the sheets by name")
    output.print_md(u"**%d** view%s placed." % (len(placed), "" if len(placed) == 1 else "s"))
    if placed:
        output.print_table(table_data=[[s.SheetNumber, s.Name, v.Name, output.linkify(s.Id)]
                                       for s, v in placed],
                           columns=["Number", "Sheet", "View", ""])
    if failed:
        output.print_md("## Not placed")
        output.print_table(table_data=[[s.SheetNumber, v.Name, w] for s, v, w in failed],
                           columns=["Number", "View", "Why"])
    if elsewhere:
        output.print_md("## View already on another sheet")
        output.print_md("*Revit puts a plan on one sheet only. Remove it from the other "
                        "sheet, or duplicate the view, then run Place Views again.*")
        output.print_table(table_data=[[s.SheetNumber, s.Name, v.Name, o]
                                       for s, v, o in elsewhere],
                           columns=["Number", "Sheet", "View", "Is on sheet"])
    if missing:
        output.print_md(u"## No view named like the sheet (%d)" % len(missing))
        output.print_table(table_data=[[s.SheetNumber, s.Name] for s in missing[:300]],
                           columns=["Number", "Sheet"])
    if already:
        output.print_md(u"*%d sheet%s already had %s view.*" % (
            len(already), "" if len(already) == 1 else "s", "its" if len(already) == 1 else "their"))


def _edit_rules(values):
    """Edit the key plan rules in Notepad; saved when they are valid."""
    path = script.get_universal_data_file("LOD_keyplan_rules", "json")
    try:
        rules = keyplan.parse_rules(values.get("keyplan_rules"))
    except keyplan.RuleError:
        rules = None
    with open(path, "w") as f:
        f.write(keyplan.dump_rules(rules) if rules is not None else values.get("keyplan_rules"))
    while True:
        from System.Diagnostics import Process
        Process.Start("notepad.exe", u'"%s"' % path).WaitForExit()
        with open(path) as f:
            raw = f.read()
        try:
            keyplan.parse_rules(raw)
        except keyplan.RuleError as error:
            if forms.alert(u"%s\n\nEdit the rules again?" % error, title=TITLE, yes=True, no=True):
                continue
            return
        values["keyplan_rules"] = raw
        settings.save(values)
        return


def _show_parameters(doc):
    from Autodesk.Revit.DB import ViewSheet
    sheet = doc.ActiveView
    if not isinstance(sheet, ViewSheet):
        picked = revit_lod.selected_sheets(doc, revit.uidoc)
        if not picked:
            forms.alert("Open a sheet (or select one in the Project Browser) first.", title=TITLE)
            return
        sheet = picked[0]
    rows = revit_lod.parameters_on(doc, sheet)
    output = _out("Sheet parameters")
    output.print_md(u"# Parameters on sheet %s - %s" % (sheet.SheetNumber, sheet.Name))
    output.print_md("*Yes/No parameters are the ones key plan rules switch on and off; "
                    "Text ones can take {floor}, {building}...*")
    if not rows:
        output.print_md("No title block or family on this sheet.")
        return
    output.print_table(table_data=[[a, b, c, d, u"yes" if e else u""] for a, b, c, d, e in rows],
                       columns=["Family : Type", "Parameter", "Kind", "Value", "Read-only"])


_SETTINGS = (
    ("lod_path", "LOD file"),
    ("title_prefix", "Title prefix left out of sheet names"),
    ("rev_param", "Sheet parameter for the revision"),
    ("area_param", "Sheet parameter for the area"),
    ("title_block", "Title block for new sheets"),
    ("keyplan_rules", "Key plan rules"),
)
SHOW = "Show the parameters of this sheet (to name the key plan rules)"


def edit_settings():
    doc = revit.doc
    while True:
        values = settings.load()
        options = []
        for key, label in _SETTINGS:
            shown = values[key]
            if key == "keyplan_rules":
                shown = u"default" if not shown.strip() else u"custom"
            elif key == "lod_path":
                shown = os.path.basename(shown)
            options.append(u"%s: %s" % (label, shown if shown != u"" else u"-"))
        options.append(SHOW)
        choice = forms.CommandSwitchWindow.show(options, message="LOD tools. Click a setting:")
        if not choice:
            return
        if choice == SHOW:
            if doc is not None:
                _show_parameters(doc)
            return
        key, label = _SETTINGS[options.index(choice)]
        if key == "lod_path":
            values["lod_path"] = u""
            _pick_lod(values)
            continue
        if key == "keyplan_rules":
            _edit_rules(values)
            continue
        if key == "title_block":
            if doc is None:
                continue
            values["title_block"] = u""
            _choose_title_block(doc, values)
            continue
        hint = {
            "title_prefix": "Text at the start of every LOD title that the sheet names leave "
                            "out, e.g. 'KEZAD Two Building - ' (empty: names are the full titles):",
            "rev_param": "Text parameter of the sheets that holds the LOD revision "
                         "(empty: revisions are not used):",
            "area_param": "Text parameter of the sheets for 'Area/Building References' "
                          "(empty: not used):",
        }[key]
        text = forms.ask_for_string(default=values[key], prompt=hint, title="LOD Settings")
        if text is None:
            continue
        values[key] = text if key == "title_prefix" else text.strip()
        settings.save(values)
