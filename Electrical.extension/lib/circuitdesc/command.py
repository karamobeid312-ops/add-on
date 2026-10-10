# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from pyrevit import forms, revit, script

from circuitdesc import describe, revit_desc, settings
from circuitdesc.describe import CHANGE, FEEDER, NAME, NAME_NUMBER, NO_FIXTURES, NOT_FOUND, \
    NUMBER_NAME

TITLE = "Circuit Description"


class _Board(forms.TemplateListItem):
    @property
    def name(self):
        return self.item[0]


class _Change(forms.TemplateListItem):
    @property
    def name(self):
        c = self.item
        return u"%s  %s:   %s   >   %s" % (c.panel, c.number, c.old or u"(blank)", c.new)


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
            table_data=[[c.panel, c.number, c.old, c.new] for c in done],
            columns=["Board", "Circuit", "Was", "Now"])
    if failed:
        output.print_md("## Not written")
        output.print_table(
            table_data=[[c.panel, c.number, u"%s" % e] for c, e in failed],
            columns=["Board", "Circuit", "Why"])
    missing = describe.by_status(found, NOT_FOUND)
    if missing:
        output.print_md("## No room found: description kept")
        output.print_md("*Their fixtures are in no room of the linked models (outside the "
                        "rooms, or the link is unloaded).*")
        output.print_table(
            table_data=[[c.panel, c.number, c.old,
                         output.linkify([e.Id for e in c.ref.Elements], "select fixtures")]
                        for c in missing],
            columns=["Board", "Circuit", "Description", ""])
    partial = [c for c in describe.by_status(found, CHANGE) if c.missing and c in done]
    if partial:
        output.print_md("## Some fixtures in no room")
        output.print_md("*Described from the fixtures that are in a room.*")
        output.print_table(
            table_data=[[c.panel, c.number, c.missing,
                         output.linkify([e.Id for e in c.ref.Elements], "select fixtures")]
                        for c in partial],
            columns=["Board", "Circuit", "Fixtures in no room", ""])
    others = []
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
    """Write the room of each circuit's fixtures to its Load Name."""
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
    if not changes:
        _show([], found, [])
        forms.alert("Nothing to change: the circuits already say their rooms, or no room "
                    "was found for them (see the report).", title=TITLE)
        return

    chosen = forms.SelectFromList.show(
        [_Change(c, checked=True) for c in changes],
        title="%s: %s (untick to keep)" % (TITLE, describe.headline(found)),
        multiselect=True, button_name="Write descriptions", width=900, height=650)
    if not chosen:
        return
    with revit.Transaction("Circuit descriptions from rooms"):
        failed = revit_desc.write(chosen)
    bad = set(id(c) for c, _ in failed)
    _show([c for c in chosen if id(c) not in bad], found, failed)


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
