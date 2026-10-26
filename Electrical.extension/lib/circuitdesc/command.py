# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import SubTransaction
from pyrevit import forms, revit, script

from circuitdesc import describe, revit_desc, revit_spares, settings
from circuitdesc.describe import CHANGE, FEEDER, LIGHTING, NAME, NAME_NUMBER, NO_FIXTURES, \
    NUMBER_NAME
from circuitdesc.spares import SECTION_30MA, SECTION_100MA, BoardPlan

TITLE = "Circuit Description"


class _Board(forms.TemplateListItem):
    @property
    def name(self):
        return self.item[0]


class _Change(forms.TemplateListItem):
    @property
    def name(self):
        c = self.item
        if isinstance(c, BoardPlan):
            return u"%s  BOARD:   %s" % (c.panel, c.text())
        text = u"%s  %s:   " % (c.panel, c.number)
        if c.new != c.old:
            text += u"%s   >   %s" % (c.old or u"(blank)", c.new)
        else:
            text += c.new or u"(blank)"
        if c.loads_changed:
            text += u"   |   " + (describe.loads_text(c.loads) or u"loads cleared")
        if c.wiring_changed:
            text += u"   |   " + describe.wiring_text(c.kind)
        return text


def _choose_boards(doc, uidoc, circuits):
    picked = [b for b in revit_desc.chosen_boards(doc, uidoc)
              if revit_desc.id_int(b.Id) in circuits]
    if picked:
        return picked
    listed = revit_desc.boards(doc, circuits)
    if not listed:
        return []
    chosen = forms.SelectFromList.show(
        [_Board(b) for b in listed], title="%s: which boards?" % TITLE,
        multiselect=True, button_name="Describe their circuits")
    return [b[1] for b in chosen or []]


def _show(done, found, failed):
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md("# Circuit descriptions")
    output.print_md(u"%d circuit%s described." % (len(done), "" if len(done) == 1 else "s"))
    if done:
        output.print_table(
            table_data=[[c.panel, c.number, c.old, c.new, describe.loads_text(c.loads)]
                        for c in done],
            columns=["Board", "Circuit", "Was", "Now", "Loads"])
    if failed:
        output.print_md("## Not written")
        output.print_table(
            table_data=[[c.panel, c.number, u"%s" % e] for c, e in failed],
            columns=["Board", "Circuit", "Why"])
    missing = [c for c in found if c.labels and not c.feeder and not c.found]
    if missing:
        output.print_md("## No room found: description kept")
        output.print_md("*Their fixtures are in no room of the linked models (outside the "
                        "rooms, or the link is unloaded).*")
        output.print_table(
            table_data=[[c.panel, c.number, c.old,
                         output.linkify([e.Id for e in c.ref.Elements], "select fixtures")]
                        for c in missing],
            columns=["Board", "Circuit", "Description", ""])
    partial = [c for c in done if c.missing and c.found]
    if partial:
        output.print_md("## Some fixtures in no room")
        output.print_md("*Described from the fixtures that are in a room.*")
        output.print_table(
            table_data=[[c.panel, c.number, c.missing,
                         output.linkify([e.Id for e in c.ref.Elements], "select fixtures")]
                        for c in partial],
            columns=["Board", "Circuit", "Fixtures in no room", ""])
    over = [c for c in found if c.overflow and not c.feeder]
    if over:
        output.print_md("## More than %d fixture types" % describe.LOAD_SLOTS)
        output.print_md("*Only the %d types with the most fixtures are in Load1 to Load%d.*"
                        % (describe.LOAD_SLOTS, describe.LOAD_SLOTS))
        output.print_table(table_data=[[c.panel, c.number] for c in over],
                           columns=["Board", "Circuit"])
    no_watts = [c for c in done if any(nos and not wpu for _, nos, wpu in c.loads)]
    if no_watts:
        output.print_md("## Fixtures with no load")
        output.print_md("*Their W PER UNIT is left blank: give the fixture family an "
                        "Apparent Load.*")
        output.print_table(
            table_data=[[c.panel, c.number,
                         u", ".join(t or u"?" for t, nos, wpu in c.loads if nos and not wpu)]
                        for c in no_watts],
            columns=["Board", "Circuit", "Types"])
    others = []
    df_names = sorted(set(c.df_param for c in found if getattr(c, "df_param", None)))
    no_df = [c for c in found if c.kind and not c.feeder and not getattr(c, "df_param", None)]
    if df_names:
        others.append(u"Diversity factor written to %s" % u", ".join(df_names))
    if no_df:
        others.append(u"%d circuit%s with no diversity factor parameter (%s): DF not written" % (
            len(no_df), "" if len(no_df) == 1 else "s", u", ".join(revit_desc.DF_NAMES)))
    no_params = [c for c in found if not getattr(c, "has_loads", True) and not c.feeder]
    if no_params:
        others.append(u"%d circuit%s without the Load1_Type ... Load6_WpU parameters: "
                      u"only the description was written" % (
                          len(no_params), "" if len(no_params) == 1 else "s"))
    feeders = describe.by_status(found, FEEDER)
    if feeders:
        others.append(u"%d circuit%s feeding other boards kept %s description" % (
            len(feeders), "" if len(feeders) == 1 else "s",
            "its" if len(feeders) == 1 else "their"))
    empty = describe.by_status(found, NO_FIXTURES)
    if empty:
        others.append(u"%d circuit%s with nothing connected left as %s" % (
            len(empty), "" if len(empty) == 1 else "s", "it is" if len(empty) == 1 else "they are"))
    for line in others:
        output.print_md("- " + line)


def run():
    """Write the room of each circuit's fixtures to its Load Name, and its
    fixtures by type to Load1_Type / _Nos / _WpU ... Load6_."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to describe the circuits.", title=TITLE)
        return
    values = settings.load()
    models = revit_desc.linked_models(doc)
    if values["host_spaces"]:
        models.append(revit_desc.Model(doc))
    if not models:
        forms.alert("No linked model is loaded: load the architectural link, whose rooms "
                    "name the circuits.", title=TITLE)
        return
    circuits = revit_desc.power_circuits(doc)
    boards = _choose_boards(doc, uidoc, circuits)
    if not boards:
        return

    found = []
    with forms.ProgressBar(title="Finding the rooms of the fixtures...") as bar:
        for i, board in enumerate(boards):
            found += revit_desc.read(board, circuits[revit_desc.id_int(board.Id)],
                                     models, values)
            bar.update_progress(i + 1, len(boards))
    found = describe.ordered(found)
    changes = describe.by_status(found, CHANGE)
    info = dict((revit_desc.id_int(c.ref.Id), (_section(c), c.watts or 0.0))
                for c in found)
    plans = [p for p in (_plan(b, info) for b in boards) if p is not None and p.changed]
    if not changes and not plans:
        _show([], found, [])
        forms.alert("Nothing to change: the circuits already say their rooms and loads, "
                    "the boards have their spares and spaces, or no room was found for "
                    "the circuits (see the report).", title=TITLE)
        return

    chosen = forms.SelectFromList.show(
        [_Change(p, checked=True) for p in plans] + [_Change(c, checked=True) for c in changes],
        title="%s: %s (untick to keep)" % (TITLE, describe.headline(found)),
        multiselect=True, button_name="Write", width=900, height=650)
    if not chosen:
        return
    chosen_plans = [c for c in chosen if isinstance(c, BoardPlan)]
    chosen = [c for c in chosen if not isinstance(c, BoardPlan)]
    lighting = {}                       # board -> its 100 mA section is all lighting
    for c in found:
        if _section(c) == SECTION_100MA:
            lighting[c.panel] = lighting.get(c.panel, True) and c.kind == LIGHTING
    with revit.Transaction("Circuit descriptions, loads, spares and spaces"):
        failed = revit_desc.write(chosen)
        board_failed = []
        for p in chosen_plans:
            sub = SubTransaction(doc)      # a board that fails is left as it was
            sub.Start()
            try:
                revit_spares.apply(p, {
                    SECTION_100MA: 16.0 if lighting.get(p.panel) else 20.0,
                    SECTION_30MA: 20.0})
                sub.Commit()
            except Exception as error:
                sub.RollBack()
                board_failed.append((p, error))
    bad = set(id(c) for c, _ in failed)
    _show([c for c in chosen if id(c) not in bad], found, failed)
    _show_boards([p for p in chosen_plans if p not in [b for b, _ in board_failed]],
                 board_failed)


def _section(circuit):
    """Lighting and FCU circuits on the 100 mA RCD, the rest on the 30 mA one."""
    if circuit.kind == LIGHTING or getattr(circuit, "fcu", False):
        return SECTION_100MA
    return SECTION_30MA


def _plan(board, info):
    try:
        return revit_spares.plan(board, info)
    except Exception:
        return None


def _show_boards(done, failed):
    output = script.get_output()
    if done:
        output.print_md("## RCD sections, spares and spaces")
        output.print_table(
            table_data=[[p.panel, p.ways,
                         u"%s, %d circuits, %d spares" % (
                             p.rcds.get(SECTION_100MA, u"-"), p.counts.get(SECTION_100MA, 0),
                             len(p.spare_slots.get(SECTION_100MA, []))),
                         u"%s, %d circuits, %d spares" % (
                             p.rcds.get(SECTION_30MA, u"-"), p.counts.get(SECTION_30MA, 0),
                             len(p.spare_slots.get(SECTION_30MA, []))),
                         len(p.spaces), len(p.moved)] for p in done],
            columns=["Board", "Ways", "Section 1 (lighting + FCU)", "Section 2 (power)",
                     "Spaces", "Moved"])
    if failed:
        output.print_md("## Boards not changed")
        output.print_table(table_data=[[p.panel, u"%s" % e] for p, e in failed],
                           columns=["Board", "Why"])


FCU_DF = u"0.9"


class _FcuCircuit(forms.TemplateListItem):
    @property
    def name(self):
        board, system = self.item
        return u"%s  %s:   DF %s   >   %s" % (
            board, system.CircuitNumber, revit_desc.read_df(system) or u"(blank)", FCU_DF)


def fcu_df():
    """Set the diversity factor of every FCU circuit to 0.9 (of the boards
    picked first, else of the whole model)."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model.", title="FCU DF")
        return
    circuits = revit_desc.power_circuits(doc)
    picked = set(revit_desc.id_int(b.Id) for b in revit_desc.chosen_boards(doc, uidoc))
    if picked:
        circuits = dict((k, v) for k, v in circuits.items() if k in picked)
    found = revit_desc.fcu_circuits(circuits)
    todo = [x for x in found if revit_desc.read_df(x[1]) != FCU_DF]
    if not todo:
        forms.alert(u"%d FCU circuit%s found, all already DF %s." % (
            len(found), "" if len(found) == 1 else "s", FCU_DF), title="FCU DF")
        return
    chosen = forms.SelectFromList.show(
        [_FcuCircuit(x, checked=True) for x in todo],
        title=u"FCU DF: %d FCU circuits to DF %s (untick to keep)" % (len(todo), FCU_DF),
        multiselect=True, button_name="Write", width=700, height=600)
    if not chosen:
        return
    done, no_param = 0, []
    with revit.Transaction("FCU circuits DF %s" % FCU_DF):
        for board, system in chosen:
            if revit_desc.write_df(system, FCU_DF):
                done += 1
            else:
                no_param.append(u"%s %s" % (board, system.CircuitNumber))
    text = u"%d FCU circuit%s set to DF %s." % (done, "" if done == 1 else "s", FCU_DF)
    if no_param:
        text += u"\n\nNo diversity factor parameter on: " + u", ".join(no_param)
    forms.alert(text, title="FCU DF")


STYLE_TEXT = {
    NUMBER_NAME: "Number + name   (012 PUMP ROOM)",
    NAME: "Name only   (PUMP ROOM)",
    NAME_NUMBER: "Name + number   (PUMP ROOM 012)",
}


def edit_settings():
    values = settings.load()
    options = [STYLE_TEXT[s] for s in describe.STYLES]
    choice = forms.CommandSwitchWindow.show(
        options, message="How is a room written? (now: %s)" % STYLE_TEXT[values["style"]])
    if choice is None:
        return
    values["style"] = describe.STYLES[options.index(choice)]
    upper = forms.alert("Write the descriptions in CAPITALS, as the panel schedules?",
                        title=TITLE, yes=True, no=True)
    values["upper"] = bool(upper)
    host = forms.alert("When a fixture is in no room of the linked models, use the rooms "
                       "and spaces of this model?", title=TITLE, yes=True, no=True)
    values["host_spaces"] = bool(host)
    settings.save(values)
